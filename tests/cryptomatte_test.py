import logging
import time
from pathlib import Path

from maya_mod.start_mayapy import run_module_in_standalone
from modules.decryptomatte import DecyrptoMatte
from modules.create_cryptomatte import CreateCryptomattes
from modules.setup_paths import get_current_modules_dir
from modules.utils import OpenImageUtil, create_file_safe_name

logging.basicConfig(level=logging.DEBUG)
LOGGER = logging.getLogger(__name__)


def alpha_over(a: float, b: float):
    """
        https://www.w3.org/TR/SVGTiny12/painting.html#CompositingSimpleAlpha
    """
    return 1.0 - (1.0 - a) * (1.0 - b)


def main():
    start_time = time.time()
    output_dir = Path(r'D:\temp\crypto_test')
    scene = Path(r'z:\__Audi\__Konfigurator\__A5_Familie\XXXXX_RS5_PA_NeMo\C_3D-Daten\AU49X_A5PA_2020_04_ND_F_01_20190910_POLY\AU49X_A5PA_2020_04_ND_F_01_20190910_POLY.csb')
    mod_dir = get_current_modules_dir()
    psd_creation_module = Path(mod_dir) / 'maya_mod/run_create_psd.py'
    psd_file = output_dir / f'{scene.stem}.psd'
    c = CreateCryptomattes(output_dir, scene, logger=LOGGER)
    c.create_cryptomattes()

    try:
        process = run_module_in_standalone(
            psd_creation_module.as_posix(),  # Path to module to run
            psd_file.as_posix(), output_dir.as_posix(), 'iff',  # Args
            Path(mod_dir).as_posix()  # Environment dir
            )
        process.wait()
    except Exception as e:
        LOGGER.error(e)

    LOGGER.info(f'Finished in {time.time() - start_time:.4f}s')


def main_old():
    beauty_img_file = Path(r'H:\tmp\crypto_2\images\tmp\beauty\test_scene_1.exr')
    img_file = Path(r'H:\tmp\crypto_2\images\tmp\crypto_material\test_scene_1.exr')

    beauty_img = OpenImageUtil.read_image(beauty_img_file)
    beauty_img = OpenImageUtil.premultiply_image(beauty_img)

    d = DecyrptoMatte(LOGGER, img_file, alpha_over_compositing=True)
    layers = d.list_layers()

    for layer_name, id_matte in d.get_mattes_by_names(layers).items():
        LOGGER.debug('Layer %s - %s', layer_name, id_matte.any(axis=-1).sum())

        # Create premultiplied
        rgba_matte = d.merge_matte_and_rgb(id_matte, beauty_img)
        repre_matte = OpenImageUtil.premultiply_image(rgba_matte)

        # Write result
        file_name = f'{create_file_safe_name(layer_name)}.tif'
        pre_img_file = img_file.parent / file_name
        OpenImageUtil.write_image(pre_img_file, repre_matte)

    d.shutdown()

    LOGGER.debug('Example matte extraction finished.')


if __name__ == '__main__':
    main()
