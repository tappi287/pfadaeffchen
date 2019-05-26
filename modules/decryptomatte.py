import json
import time
import logging
import mmh3
import os
import struct

import numpy as np

import OpenImageIO as oiio
from OpenImageIO import ImageBuf
from pathlib import Path
from typing import List


class DecyrptoMatte:
    """ Most of this code is shamelessly stolen from original cryptomatte_arnold unit tests under BSD-3 license
        https://github.com/Psyop/CryptomatteArnold
        https://github.com/Psyop/Cryptomatte
    """
    empty_pixel_threshold = 5  # Minimum number of opaque pixels a matte must contain
    empty_value_threshold = 0.2  # Minimum sum of all coverage values of all pixels

    def __init__(self, logger, img_file: Path, alpha_over_compositing=False):
        global LOGGER
        LOGGER = logger
        if logger is None:
            logging.basicConfig(level=logging.DEBUG)
            LOGGER = logging.getLogger(__name__)

        self.alpha_over_compositing = alpha_over_compositing

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
        """ Store the manifest contents from extracted metadata """
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
            LOGGER.debug('ID: %s: %s', layer_name, id_hex_str)
            layer_names.append(layer_name)

        return layer_names

    def crypto_metadata(self) -> dict:
        """ Returns dictionary of key, value of cryptomatte metadata """
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
        for id_val, id_matte in self._get_mattes_per_id(list(id_to_names.keys())).items():
            id_mattes_by_name[id_to_names.get(id_val)] = id_matte

        return id_mattes_by_name

    def _get_mattes_per_id(self, target_ids: List[float]) -> dict:
        """
            Get a alpha coverage matte for every given id
            as dict {id_value[float]: coverage_matte[np.array]}

            Matte arrays are single channel two dimensional arrays(shape: image_height, image_width)
        """
        if not target_ids:
            return dict()

        img_nested_md = self.sorted_crypto_metadata()

        w, h = self.img.spec().width, self.img.spec().height

        start = time.time()
        id_mattes = self._iterate_image(0, 0, w, h, img_nested_md, target_ids)

        # Purge mattes below threshold value
        for id_val in target_ids:
            v, p = id_mattes[id_val].max(), id_mattes[id_val].any(axis=-1).sum()

            if v < self.empty_value_threshold and p < self.empty_pixel_threshold:
                LOGGER.debug('Purging empty coverage matte: %s %s', v, p)
                id_mattes.pop(id_val)

        # --- DEBUG info ---
        LOGGER.debug(f'Iterated image : {w:04d}x{h:04d} - with {len(target_ids)} ids.')
        LOGGER.debug(f'Id Matte extraction finished in {time.time() - start:.4f}s')

        return id_mattes

    def _iterate_image(self, start_x: int, start_y: int, width: int, height: int,
                       img_nested_md: dict, target_ids: list):
        id_mattes = {id_val: np.zeros((height, width), dtype=np.float32) for id_val in target_ids}

        for y in range(start_y, start_y + height):
            for x in range(start_x, start_x + width):
                result_pixel = self.img.getpixel(x, y)

                for cryp_key in img_nested_md:
                    result_id_cov = self._get_id_coverage_dict(
                        result_pixel,
                        img_nested_md[cryp_key]["ch_pair_idxs"]
                        )

                    high_rank_id, coverage_sum = 0.0, 0.0

                    for id_val, coverage in result_id_cov.items():
                        if id_val in id_mattes:
                            # Sum coverage per id
                            id_mattes[id_val][y][x] += coverage
                            # Sum overall coverage for this pixel of all ids
                            coverage_sum += coverage

                            if not high_rank_id:
                                # Store the id with the highest rank
                                # for this pixel (first entry in result_id_cov)
                                high_rank_id = id_val

                    # Highest ranked Id will be set fully opaque for the whole pixel
                    # if multiple Ids are contributing to this pixel
                    # getting matte ready for alpha over operations eg. Photoshop
                    if self.alpha_over_compositing and high_rank_id:
                        if id_mattes[high_rank_id][y][x] != coverage_sum:
                            id_mattes[high_rank_id][y][x] = coverage_sum

            if not y % 256:
                LOGGER.debug('Reading cryptomatte at vline: %s (%sx%s)', y, width, height)

        return id_mattes

    @staticmethod
    def _get_id_coverage_dict(pixel_values, ch_pair_idxs):
        return {
            pixel_values[x]: pixel_values[y]
            for x, y, in ch_pair_idxs if (x != 0.0 or y != 0.0)
            }

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
    def id_to_rgb(id_float):
        """ This takes the hashed id and converts it to a preview color """
        import ctypes
        bits = ctypes.cast(ctypes.pointer(ctypes.c_float(id_float)), ctypes.POINTER(ctypes.c_uint32)).contents.value

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
