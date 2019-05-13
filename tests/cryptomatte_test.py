import logging
from pathlib import Path

import numpy as np
from modules.decryptomatte import DecyrptoMatte, write_image

logging.basicConfig(level=logging.DEBUG)
LOGGER = logging.getLogger(__name__)

def main():
    img_file = Path(r'H:\tmp\crypto_2\images\tmp\crypto_material\test_scene.exr')
    d = DecyrptoMatte(LOGGER, img_file)
    layers = d.list_layers()
    id_mattes = d.get_mattes_by_names(layers)

    for layer_name, id_matte in id_mattes.items():
        eight_bit_matte = np.uint8(id_matte * 255)
        rgba_matte = d.grayscale_to_rgba(eight_bit_matte)
        matte_img_file = img_file.parent / f'{layer_name}.png'

        write_image(matte_img_file, rgba_matte)

    LOGGER.debug('Example matte extraction finished. %s', len(id_mattes))


if __name__ == '__main__':
    main()
