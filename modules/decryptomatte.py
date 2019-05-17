import json
import logging
import mmh3
import os
import struct

import OpenImageIO as oiio
from OpenImageIO import ImageBuf, ImageOutput, ImageSpec, ImageBufAlgo
from pathlib import Path
from typing import List, Dict

import numpy as np


class DecyrptoMatte:
    """ Most of this code is shamelessly stolen from original cryptomatte_arnold unit tests under BSD-3 license
        https://github.com/Psyop/Cryptomatte
        https://github.com/Psyop/CryptomatteArnold
    """
    empty_pixel_threshold = 5  # Minimum number of opaque pixels a matte must contain
    empty_value_threshold = 0.2  # Minimum sum of all coverage values of all pixels

    def __init__(self, logger, img_file: Path):
        global LOGGER
        LOGGER = logger
        if logger is None:
            logging.basicConfig(level=logging.DEBUG)
            LOGGER = logging.getLogger(__name__)

        self.img_file = img_file
        self.img = ImageBuf(img_file.as_posix())
        self.metadata_cache = {}
        self.manifest_cache = {}

    def shutdown(self):
        """ Release resources """
        try:
            del self.metadata_cache
            del self.manifest_cache
            self.img.clear()
            del self.img
            oiio.ImageCache().invalidate(self.img_file.as_posix())
        except Exception as e:
            LOGGER.error('Error closing img buf: %s', e)

    def _create_manifest_cache(self, metadata):
        if not self.manifest_cache:
            manifest = [m for k, m in metadata.items() if k.endswith('manifest')]
            if manifest:
                self.manifest_cache = json.loads(manifest[0])

    def list_layers(self):
        """ List available ID layers of this cryptomatte image """
        metadata = self.crypto_metadata()
        layer_names = list()

        self._create_manifest_cache(metadata)
        LOGGER.info('Found Cryptomatte with %s id layers', len(self.manifest_cache))

        # List ids in cryptomatte
        for layer_name, id_hex_str in self.manifest_cache.items():
            LOGGER.debug('ID Layer: %s: %s', layer_name, id_hex_str)
            layer_names.append(layer_name)

        return layer_names

    def crypto_metadata(self) -> dict:
        """Returns dictionary of key, value of cryptomatte metadata"""
        if self.metadata_cache:
            return self.metadata_cache

        metadata = {
            a.name: a.value
            for a in self.img.spec().extra_attribs
            if a.name.startswith("cryptomatte")
        }

        for key in metadata.keys():
            if key.endswith("/manif_file"):
                sidecar_path = os.path.join(
                    os.path.dirname(self.img.name), metadata[key]
                    )
                with open(sidecar_path) as f:
                    metadata[key.replace("manif_file", "manifest")] = f.read()

        self.metadata_cache = metadata
        return metadata

    def sorted_crypto_metadata(self):
        """
        Gets a dictionary of the cryptomatte metadata, interleved by cryptomatte stream.

        for example:
            {"crypto_object": {"name": crypto_object", ... }}

        Also includes ID coverage pairs in subkeys, "ch_pair_idxs" and "ch_pair_names".
        """
        img_md = self.crypto_metadata()
        cryptomatte_streams = {}

        for key, value in img_md.items():
            prefix, cryp_key, cryp_md_key = key.split("/")
            name = img_md["/".join((prefix, cryp_key, "name"))]
            cryptomatte_streams[name] = cryptomatte_streams.get(name, {})
            cryptomatte_streams[name][cryp_md_key] = value

        for cryp_key in cryptomatte_streams:
            name = cryptomatte_streams[cryp_key]["name"]
            ch_id_coverages = []
            ch_id_coverage_names = []
            channels_dict = {
                ch: i
                for i, ch in enumerate(self.img.spec().channelnames)
            }
            for i, ch in enumerate(self.img.spec().channelnames):
                if not ch.startswith(name):
                    continue
                if ch.startswith("%s." % name):
                    continue
                if ch.endswith(".R"):
                    red_name = ch
                    green_name = "%s.G" % ch[:-2]
                    blue_name = "%s.B" % ch[:-2]
                    alpha_name = "%s.A" % ch[:-2]

                    red_idx = i
                    green_idx = channels_dict[green_name]
                    blue_idx = channels_dict[blue_name]
                    alpha_idx = channels_dict[alpha_name]

                    ch_id_coverages.append((red_idx, green_idx))
                    ch_id_coverages.append((blue_idx, alpha_idx))
                    ch_id_coverage_names.append((red_name, green_name))
                    ch_id_coverage_names.append((blue_name, alpha_name))
            cryptomatte_streams[cryp_key]["ch_pair_idxs"] = ch_id_coverages
            cryptomatte_streams[cryp_key]["ch_pair_names"] = ch_id_coverage_names
        return cryptomatte_streams

    def get_mattes_by_names(self, layer_names: List[str]) -> dict:
        id_to_names = dict()

        if not self.manifest_cache:
            self._create_manifest_cache(self.crypto_metadata())

        for name in layer_names:
            if name in self.manifest_cache:
                id_val = self.hex_str_to_id(self.manifest_cache.get(name))
                id_to_names[id_val] = name

        id_mattes_by_name = dict()
        for id_val, id_matte in self._get_mattes(list(id_to_names.keys())).items():
            id_mattes_by_name[id_to_names.get(id_val)] = id_matte

        return id_mattes_by_name

    def _get_mattes(self, target_ids: List[float]) -> dict:
        """
            Get a alpha coverage matte for every given id
            as dict {id_value[float]: coverage_matte[np.array]}

            Matte arrays are single channel two dimensional arrays(shape: image_height, image_width)
        """
        if not target_ids:
            return dict()

        img_nested_md = self.sorted_crypto_metadata()
        result_pixel, result_id_cov = None, None

        # Create dictionary that will store the coverage matte arrays per id
        w, h = self.img.spec().width, self.img.spec().height
        id_mattes = {id_val: np.zeros((h, w), dtype=np.float32) for id_val in target_ids}

        for y in range(0, h):
            for x in range(0, w):
                result_pixel = self.img.getpixel(x, y)

                for cryp_key in img_nested_md:
                    result_id_cov = self.get_id_coverage_dict(
                        result_pixel,
                        img_nested_md[cryp_key]["ch_pair_idxs"]
                        )

                    """
                    # Full coverage per Pixel, if eg. 2 IDs are contributing so that mask is fully opaque

                    pixel_id_coverage = 0.0  # Coverage from -any- ID
                    for id_val, coverage in result_id_cov.items():
                        if id_val in id_mattes:
                            pixel_id_coverage += coverage
                    """
                    for id_val, coverage in result_id_cov.items():
                        if id_val in id_mattes:
                            # Sum coverage per id
                            id_mattes[id_val][y][x] += coverage

            if not y % 200:
                LOGGER.debug('Iterating pixel row %s of %s', y, h)

        del result_id_cov, result_pixel

        # Purge mattes below threshold value
        for id_val in target_ids:
            v, p = id_mattes[id_val].max(), id_mattes[id_val].any(axis=-1).sum()

            if v < self.empty_value_threshold and p < self.empty_pixel_threshold:
                LOGGER.debug('Purging empty coverage matte: %s %s', v, p)
                id_mattes.pop(id_val)

        # --- DEBUG info ---
        LOGGER.debug(f'Iterated image : {w:04d}x{h:04d} - with {len(target_ids)} ids.')

        return id_mattes

    @staticmethod
    def get_id_coverage_dict(pixel_values, ch_pair_idxs):
        return {
            pixel_values[x]: pixel_values[y]
            for x, y, in ch_pair_idxs if (x != 0.0 or y != 0.0)
            }

    @staticmethod
    def manifest_str_to_dict(mainfest_str: str) -> dict:
        return json.loads(mainfest_str)

    @staticmethod
    def mm3hash_float(name) -> float:
        hash_32 = mmh3.hash(name)
        exp = hash_32 >> 23 & 255
        if (exp == 0) or (exp == 255):
            hash_32 ^= 1 << 23

        packed = struct.pack('<L', hash_32 & 0xffffffff)
        return struct.unpack('<f', packed)[0]

    @staticmethod
    def hex_str_to_id(id_hex_string: str) -> float:
        """ Converts a manifest hex string to a float32 id value """
        packed = struct.Struct("=I").pack(int(id_hex_string, 16))
        return struct.Struct("=f").unpack(packed)[0]

    @staticmethod
    def id_to_hex_str(id_float: float) -> str:
        return "{0:08x}".format(struct.unpack('<I', struct.pack('<f', id_float))[0])

    @staticmethod
    def id_to_rgb(id):
        """ This takes the hashed id and converts it to a preview color """
        import ctypes
        bits = ctypes.cast(ctypes.pointer(ctypes.c_float(id)), ctypes.POINTER(ctypes.c_uint32)).contents.value

        mask = 2 ** 32 - 1
        return [0.0, float((bits << 8) & mask) / float(mask), float((bits << 16) & mask) / float(mask)]

    @classmethod
    def layer_hash(cls, layer_name):
        """ Convert a layer name to hash hex string """
        return cls.id_to_hex_str(cls.mm3hash_float(layer_name))[:-1]

    @classmethod
    def merge_matte_and_rgb(cls, matte: np.ndarray, rgb_img: np.ndarray=None):
        """ Merge matte and rgb img array to rgba img array"""
        h, w = matte.shape
        rgba = np.empty((h, w, 4), dtype=matte.dtype)

        if rgb_img is None:
            rgba[:, :, 3] = rgba[:, :, 2] = rgba[:, :, 1] = rgba[:, :, 0] = matte
        else:
            rgba[:, :, 3] = matte
            rgba[:, :, 2] = rgb_img[:, :, 2]
            rgba[:, :, 1] = rgb_img[:, :, 1]
            rgba[:, :, 0] = rgb_img[:, :, 0]

        return rgba


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
            LOGGER.error('Can not create image with Pixel data in this shape. Expecting 4 channels(RGBA).')
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
            output.write_image(pixels)
        else:
            LOGGER.error('Could not open image file for writing: %s: %s', file.name, output.geterror())

        output.close()
