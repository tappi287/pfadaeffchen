import OpenImageIO as oiio
from OpenImageIO import ImageBuf, ImageBufAlgo, ImageSpec
import logging
from pathlib import Path
from queue import Empty, Queue
from threading import Thread

import numpy as np

from modules.decryptomatte import DecyrptoMatte, write_image
from modules.utils import create_file_safe_name

logging.basicConfig(level=logging.DEBUG)
LOGGER = logging.getLogger(__name__)


def read_image(img_file: Path, format: str=''):
    img_input = oiio.ImageInput.open(img_file.as_posix())
    return img_input.read_image(format=format)

"""
Examples:
ImageBuf A ("a.exr");
ImageBuf Inverse = ImageBufAlgo::invert (Inverse, A);
// In this example, we are careful to deal with alpha in an RGBA image.
// First we copy A to Inverse, un-premultiply the color values by alpha,
// invert just the color channels in-place, and then re-premultiply the
// colors by alpha.
roi = A.roi();
roi.chend = 3; // Restrict roi to only R,G,B
ImageBuf Inverse = ImageBufAlgo::unpremult (A);
ImageBufAlgo::invert (Inverse, Inverse, roi);
ImageBufAlgo::premult (Inverse, Inverse);
"""


def repremultiply_image(img_pixels: np.array) -> np.array:
    if len(img_pixels.shape) < 3:
        LOGGER.error('Can not create image with Pixel data in this shape. Expecting 4 channels(RGBA).')
        return

    h, w, c = img_pixels.shape
    img_spec = ImageSpec(w, h, c, img_pixels.dtype.name)

    a = ImageBuf(img_spec)
    a.set_pixels(img_spec.roi_full, img_pixels)
    inverse = ImageBufAlgo.invert(a, img_spec.roi_full)

    only_rgb = a.roi
    only_rgb.chend = 3

    unpre_a = ImageBufAlgo.unpremult(a)
    ImageBufAlgo.invert(inverse, inverse, only_rgb)
    ImageBufAlgo.premult(inverse, a)

    return inverse.get_pixels(img_spec.format, img_spec.roi_full)




class CreateMattesThreaded:
    def __init__(self, img_file: Path, beauty_img_file: Path=None, out_dir: Path=None, max_threads=8):
        self.img_file = img_file
        self.out_dir = out_dir

        self.beauty = None
        if beauty_img_file:
            self.beauty = read_image(beauty_img_file, format='uint8')

        self.max_threads = max_threads
        self.q = Queue()

    def start(self):
        d = DecyrptoMatte(LOGGER, self.img_file)
        for layer in d.list_layers():
            self.q.put_nowait(layer)

        obj_per_thread = min(12, max(4, int(self.q.qsize() / self.max_threads)))

        worker_ls = list()
        for t in range(0, self.max_threads):
            worker = MatteWorker(self.img_file, self.out_dir, self.beauty, self.q, obj_per_thread)
            worker_ls.append(worker)
            worker.start()

        for worker in worker_ls:
            worker.join()


class MatteWorker(Thread):
    def __init__(self, img_file: Path, out_dir: Path, beauty, q: Queue, obj_per_thread: int):
        super(MatteWorker, self).__init__()
        self.img_file, self.beauty, self.out_dir = img_file, beauty, out_dir
        self.obj_per_thread, self.q = obj_per_thread, q

    def run(self):
        d = DecyrptoMatte(LOGGER, self.img_file)

        while True:
            # Receive list of layers to work through
            layer = list()
            for i in range(0, self.obj_per_thread):
                try:
                    layer.append(self.q.get_nowait())
                except Empty:
                    break

            if not layer:
                break

            # Start working
            LOGGER.debug('Matte thread starts to extract id layer %s', layer)
            id_mattes = d.get_mattes_by_names(layer)

            for layer_name, id_matte in id_mattes.items():
                LOGGER.debug('Creating matte: %s', layer_name)

                if self.out_dir:
                    matte_img_file = self.out_dir / f'{create_file_safe_name(layer_name)}.png'
                else:
                    matte_img_file = self.img_file.parent / f'{create_file_safe_name(layer_name)}.png'

                write_image(
                    matte_img_file,
                    d.grayscale_to_rgba(np.uint8(id_matte * 255), self.beauty)
                    )

            del id_mattes


def main():
    img_file = Path(r'I:\Nextcloud\py\maya_scripts\_test_scene\images\tmp\crypto_material\test_scene.exr')
    beauty_img_file = Path(r'I:\Nextcloud\py\maya_scripts\_test_scene\images\tmp\beauty\test_scene_1.exr')
    beauty_img = read_image(beauty_img_file, format='uint8')

    # matte_worker = CreateMattesThreaded(img_file, beauty_img_file)
    # matte_worker.start()

    d = DecyrptoMatte(LOGGER, img_file)
    layers = d.list_layers()

    for layer_name, id_matte in d.get_mattes_by_names(layers).items():
        LOGGER.debug('Layer %s - %s', layer_name, id_matte.any(axis=-1).sum())

        rgba_matte = d.grayscale_to_rgba(np.uint8(id_matte * 255), beauty_img)
        repre_matte = repremultiply_image(rgba_matte)
        matte_img_file = img_file.parent / f'{layer_name}.png'
        repre_img_file = img_file.parent / f'{layer_name}_repremul.png'

        write_image(matte_img_file, rgba_matte)
        write_image(repre_img_file, repre_matte)
    LOGGER.debug('Example matte extraction finished.')


if __name__ == '__main__':
    main()
