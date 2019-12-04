#! usr/bin/python_3
import os
import re
import shutil
from pathlib import Path
from typing import List, Union, Tuple

import OpenImageIO as oiio
import numpy as np
from lxml import etree

from modules.setup_log import setup_logging
from OpenImageIO import ImageBufAlgo, ImageSpec, ImageBuf, ImageOutput

from modules.setup_paths import get_user_directory

LOGGER = setup_logging(__name__)


def create_file_safe_name(filename: str) -> str:
    """ Replace any non alphanumeric characters from a string expect minus/underscore/period """
    return re.sub('[^\\w\\-_\\.]', '_', filename)


class OpenImageUtil:
    @classmethod
    def get_image_resolution(cls, img_file: Path) -> (int, int):
        img_input = cls._image_input(img_file)

        if img_input:
            res_x, res_y = img_input.spec().width, img_input.spec().height
            img_input.close()
            del img_input
            return res_x, res_y
        return 0, 0

    @classmethod
    def premultiply_image(cls, img_pixels: np.array) -> np.array:
        """ Premultiply a numpy image with itself """
        a = cls.np_to_imagebuf(img_pixels)
        ImageBufAlgo.premult(a, a)

        return a.get_pixels(a.spec().format, a.spec().roi_full)

    @staticmethod
    def get_numpy_oiio_img_format(np_array: np.ndarray):
        """ Returns either float or 8 bit integer format"""
        img_format = oiio.FLOAT
        if np_array.dtype != np.float32:
            img_format = oiio.UINT8

        return img_format

    @classmethod
    def np_to_imagebuf(cls, img_pixels: np.array):
        """ Load a numpy array 8/32bit to oiio ImageBuf """
        if len(img_pixels.shape) < 3:
            LOGGER.error('Can not create image with pixel data in this shape. Expecting 4 channels(RGBA).')
            return

        h, w, c = img_pixels.shape
        img_spec = ImageSpec(w, h, c, cls.get_numpy_oiio_img_format(img_pixels))

        img_buf = ImageBuf(img_spec)
        img_buf.set_pixels(img_spec.roi_full, img_pixels)

        return img_buf

    @classmethod
    def _image_input(cls, img_file: Path):
        """ CLOSE the returned object after usage! """
        img_input = oiio.ImageInput.open(img_file.as_posix())

        if img_input is None:
            LOGGER.error('Error reading image: %s', oiio.geterror())
            return
        return img_input

    @classmethod
    def read_image(cls, img_file: Path, format: str=''):
        img_input = cls._image_input(img_file)

        if not img_input:
            return None

        # Read out image data as numpy array
        img = img_input.read_image(format=format)
        img_input.close()

        return img

    @classmethod
    def write_image(cls, file: Path, pixels: np.array):
        output = ImageOutput.create(file.as_posix())
        if not output:
            LOGGER.error('Error creating oiio image output:\n%s', oiio.geterror())
            return

        if len(pixels.shape) < 3:
            LOGGER.error('Can not create image with Pixel data in this shape. Expecting 3 or 4 channels(RGB, RGBA).')
            return

        h, w, c = pixels.shape
        spec = ImageSpec(w, h, c, cls.get_numpy_oiio_img_format(pixels))

        result = output.open(file.as_posix(), spec)
        if result:
            try:
                output.write_image(pixels)
            except Exception as e:
                LOGGER.error('Could not write Image: %s', e)
        else:
            LOGGER.error('Could not open image file for writing: %s: %s', file.name, output.geterror())

        output.close()


def find_deltagen_scene_pos_file(scene_file: Union[str, Path]) -> Union[Path, None]:
    scene_file = Path(scene_file)
    pos_file = scene_file.with_suffix('.pos')

    if pos_file.exists():
        return pos_file


def find_deltagen_scene_texture_path_file(scene_file: Union[str, Path]) -> Union[Path, None]:
    scene_file = Path(scene_file)
    tp_file = scene_file.with_suffix('.csb.texturePath')

    if tp_file.exists():
        return tp_file


def scene_file_to_render_scene_file(scene_file):
    """ Scene_file.abc -> Scene_file_render.mb """
    base_dir = os.path.dirname(scene_file)
    scene_name = os.path.splitext(os.path.basename(scene_file))[0]
    render_scene_name = scene_name + '_render.mb'
    return os.path.join(base_dir, render_scene_name)


class MergeLayerByName:
    """
        Identify layers matching the name of their DeltaGen origin target look
        and merge them with the most common source look read from DeltaGen POS variants file.

            Eg.:
            t_seat_a -> leather_black
            t_seat_b -> leather_black

            Return a appropriate mapping dict so we can merge those layer mattes together
    """
    def __init__(self, layer_names: List[str], scene_file: Path):
        self.layer_names = layer_names
        self.scene_file = Path(scene_file)
        self.pos_file = find_deltagen_scene_pos_file(scene_file)

    def create_layer_mapping(self) -> dict:
        if self.pos_file is None or not self.pos_file.exists():
            return dict()

        return self._read_xml()

    def _read_xml(self) -> dict:
        mapping = dict()

        with open(self.pos_file.as_posix(), 'rb') as f:
            try:
                et = etree.parse(f)
            except Exception as e:
                LOGGER.error('Error parsing POS file for layer mapping: %s', e)
                return mapping

        for e in et.iterfind('*/actionList/action[@type="appearance"]'):
            actor = e.find('actor')
            value = e.find('value')

            if actor is not None and value is not None:
                if actor.text in self.layer_names:
                    mapping[actor.text] = value.text
                    self.layer_names.remove(actor.text)

        return mapping


class MoveJobSceneFile:
    job_dir_number = 0
    job_dir_name = 'jobdir_'
    local_work_dir = None

    @classmethod
    def _file_to_local_work_dir_file(cls, file):
        """ Move file location to local work dir """
        scene_dir = os.path.join(cls.local_work_dir, f'{cls.job_dir_name}{cls.job_dir_number:03d}')
        cls.create_dir(scene_dir)

        return os.path.join(scene_dir, os.path.split(os.path.basename(file))[1])

    @classmethod
    def get_local_work_dir(cls) -> str:
        if not cls.local_work_dir:
            cls.local_work_dir = cls.create_local_work_dir()

            if not os.path.exists(cls.local_work_dir):
                return str()

        return cls.local_work_dir

    @classmethod
    def move_scene_file_to_local_location(cls, scene_file: str) -> str:
        if not cls.get_local_work_dir():
            return str()

        pos_file, texture_path_file = cls.get_additional_scene_files(scene_file)
        cls.job_dir_number += 1

        try:
            result = shutil.copy(scene_file, cls._file_to_local_work_dir_file(scene_file))
            LOGGER.info('Copied scene file to local working directory: %s', result)

            if pos_file:
                pos_file = pos_file.as_posix()
                result = shutil.copy(pos_file, cls._file_to_local_work_dir_file(pos_file))
                LOGGER.info('Copied POS scene file to local working directory: %s', result)

            if texture_path_file:
                texture_path_file = texture_path_file.as_posix()
                result = shutil.copy(texture_path_file, cls._file_to_local_work_dir_file(texture_path_file))
                LOGGER.info('Copied texturePath scene file to local working directory: %s', result)
        except Exception as e:
            LOGGER.warning('Could not copy files to local destination: %s', e)
            return str()

        LOGGER.info('Updated scene file location: %s', cls._file_to_local_work_dir_file(scene_file))
        return cls._file_to_local_work_dir_file(scene_file)

    @classmethod
    def delete_local_scene_files(cls, scene_file):
        local_work_dir = cls.get_local_work_dir()
        if not local_work_dir:
            return

        if Path(scene_file).parent.parent != Path(local_work_dir):
            LOGGER.warning('Tried to delete local job files but job scene file '
                           'path is outside local working directory!\n'
                           'Job dir: %s\n'
                           'local dir: %s\n',
                           Path(scene_file.parent.parent), Path(local_work_dir))
            return

        cls.delete_local_dir(Path(scene_file).parent)
        LOGGER.info('Deleted local scene file directory: %s', Path(scene_file).parent)

    @classmethod
    def create_local_work_dir(cls) -> str:
        local_work_dir = os.path.join(get_user_directory(), '_work')
        if cls.create_dir(local_work_dir):
            return local_work_dir

        return str()

    @staticmethod
    def create_dir(directory_path) -> bool:
        try:
            if not os.path.exists(directory_path):
                os.mkdir(directory_path)
        except Exception as e:
            LOGGER.warning('Could not create or access directory: %s', e)
            return False
        return True

    @classmethod
    def clear_local_work_dir(cls):
        """ Deletes and re-create a clean local work directory """
        local_work_dir = cls.get_local_work_dir()
        if not local_work_dir:
            return

        cls.delete_local_dir(local_work_dir)
        cls.local_work_dir = cls.create_local_work_dir()

    @staticmethod
    def delete_local_dir(directory):
        try:
            if os.path.exists(directory):
                shutil.rmtree(directory)
        except Exception as e:
            LOGGER.warning(e)

    @staticmethod
    def get_additional_scene_files(scene_file) -> Tuple[Union[Path, None], Union[Path, None]]:
        pos_file = find_deltagen_scene_pos_file(scene_file)
        texture_path_file = find_deltagen_scene_texture_path_file(scene_file)
        return pos_file, texture_path_file
