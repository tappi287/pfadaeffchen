import OpenImageIO as oiio
import json
import logging
import mmh3
import os
import struct
from OpenImageIO import ImageBuf, ImageOutput, ImageSpec
from pathlib import Path
from typing import List, Dict

import numpy as np


class DecyrptoMatte:
    """ Most of this code is shamelessly stolen from original cryptomatte_arnold unit tests under BSD-3 license
        https://github.com/Psyop/Cryptomatte
        https://github.com/Psyop/CryptomatteArnold
    """
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

    def list_layers(self):
        """ List available ID layers of this cryptomatte image """
        metadata = self.crypto_metadata()
        layer_names = list()

        if not self.manifest_cache:
            manifest = [m for k, m in metadata.items() if k.endswith('manifest')]
            if manifest:
                self.manifest_cache = json.loads(manifest[0])

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

        # Create dictionary that will store the
        # coverage matte per id
        id_mattes = {id_val: list() for id_val in target_ids}

        for y in range(0, self.img.spec().height):
            matte_coverage_row_values = {id_val: list() for id_val in target_ids}

            for x in range(0, self.img.spec().width):
                result_pixel = self.img.getpixel(x, y)
                coverage_pixel = {id_val: 0.0 for id_val in target_ids}

                for cryp_key in img_nested_md:
                    result_id_cov = self.get_id_coverage_dict(
                        result_pixel,
                        img_nested_md[cryp_key]["ch_pair_idxs"]
                        )

                    for id_val, coverage in result_id_cov.items():
                        if id_val:
                            # Sum coverage per id
                            coverage_pixel[id_val] += coverage

                # Update row values
                for id_val in target_ids:
                    matte_coverage_row_values[id_val].append(coverage_pixel[id_val])

            # Append this image row coverage values
            for id_val in target_ids:
                id_mattes[id_val].append(matte_coverage_row_values[id_val])

        # Convert result to numpy array
        for id_val in target_ids:
            id_mattes[id_val] = np.array(id_mattes[id_val])

        # DEBUG info
        LOGGER.debug(f'Iterated image : {self.img.spec().width:04d}x{self.img.spec().height:04d} - '
                     f'for {len(target_ids)} ids.')
        for matte in id_mattes.values():
            if matte is not None:
                break
        else:
            matte = np.empty((1, 1))
        LOGGER.debug(f'Matte dimension: {matte.shape[1]:04d}x{matte.shape[0]:04d}')

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

    @staticmethod
    def grayscale_to_rgba(im):
        """ Convert single channel(grayscale) numpy array to 4 channel rgba 8bit """
        w, h = im.shape
        ret = np.empty((w, h, 4), dtype=np.uint8)
        ret[:, :, 3] = ret[:, :, 2] =  ret[:, :, 1] =  ret[:, :, 0] = im
        return ret


def write_image(file: Path, pixels: np.array):
    output = ImageOutput.create(file.as_posix())
    if not output:
        LOGGER.error('Error creating oiio image output:\n%s', oiio.geterror())
        return

    if len(pixels.shape) < 3:
        LOGGER.error('Can not create image with Pixel data in this shape. Expecting 3 or 4 channels(RGB, RGBA).')
        return

    h, w, c = pixels.shape
    spec = ImageSpec(w, h, c, pixels.dtype.name)

    result = output.open(file.as_posix(), spec)
    if result:
        output.write_image(pixels)
    else:
        LOGGER.error('Could not open image file for writing: %s: %s', file.name, output.geterror())

    output.close()
