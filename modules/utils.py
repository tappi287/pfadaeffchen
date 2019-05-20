import re
from pathlib import Path

import OpenImageIO as oiio
import numpy as np
from modules.setup_log import setup_logging
from OpenImageIO import ImageBufAlgo, ImageSpec, ImageBuf, ImageOutput


LOGGER = setup_logging(__name__)


def create_file_safe_name(filename: str) -> str:
    """ Replace any non alphanumeric characters from a string expect minus/underscore/period """
    return re.sub('[^\\w\\-_\\.]', '_', filename)


class OpenImageUtil:
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

    @staticmethod
    def read_image(img_file: Path, format: str=''):
        img_input = oiio.ImageInput.open(img_file.as_posix())

        if img_input is None:
            LOGGER.error('Error reading image: %s', oiio.geterror())
            return

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
