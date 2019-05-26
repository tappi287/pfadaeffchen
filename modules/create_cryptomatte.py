from pathlib import Path

from modules.app_globals import ImgParams
from modules.decryptomatte import DecyrptoMatte
from modules.utils import OpenImageUtil, MergeLayerByName, create_file_safe_name


class CreateCryptomattes:
    def __init__(self, output_dir: Path, scene_file: Path, logger=None):
        """
        Search for beauty and cryptomatte aov file output and create image file per id layer

        :param output_dir:
        :param scene_file:
        :param logger:
        """
        self.img_util = OpenImageUtil()
        self.output_dir = output_dir
        self.scene = scene_file
        self.cryptomatte_dir_name = ImgParams.cryptomatte_dir_name
        self.cryptomatte_out_file_ext = ImgParams.cryptomatte_out_file_ext

        if logger:
            global LOGGER
            LOGGER = logger

    def _find_files(self):
        beauty_img = None

        img_file = [i for i in Path(self.output_dir / self.cryptomatte_dir_name).glob(
                    f'*.{ImgParams.extension_arnold}') if i.exists()]
        beauty_f = [i for i in Path(self.output_dir / 'beauty').glob(
                    f'*.{ImgParams.extension_arnold}') if i.exists()]

        # Check that cryptomatte aov exr exists
        if img_file:
            img_file = img_file[0]

        # Use beauty render if available
        if beauty_f:
            beauty_img = self.img_util.read_image(beauty_f[0])

        return img_file, beauty_img

    def create_cryptomattes(self):
        """ Extract cryptomattes to files and return image_file_watcher dict """
        img_file_dict, beauty_img = dict(), None
        img_file, beauty_img = self._find_files()
        if not img_file:
            return img_file_dict, img_file_dict

        # Decrypt all Cryptomatte id layers to a layer_name/matte pair
        d = DecyrptoMatte(LOGGER, img_file)
        layers = d.list_layers()
        id_mattes = d.get_mattes_by_names(layers)

        # Prepare merging of layers target->source looks(DeltaGen specific)
        output_mattes = dict()
        layer_re_mappping = MergeLayerByName(layers, self.scene).create_layer_mapping()

        # ---
        # --- Merge target look IDs if DeltaGen POS file found ---
        for layer_name, id_matte in id_mattes.items():
            # eg. leather_black = t_seat_a
            layer_remap = layer_re_mappping.get(layer_name)

            if layer_remap:
                if layer_remap not in output_mattes:
                    # Create matte entry for eg. leather_black
                    output_mattes[layer_remap] = id_matte
                else:
                    # Merge with existing id matte eg. t_seat_a + t_seat_b
                    output_mattes[layer_remap] += id_matte
            else:
                # No remap necessary
                output_mattes[layer_name] = id_matte

        # ---
        # --- Write the mattes to disk ---
        for layer_name, id_matte in output_mattes.items():
            # Combine beauty and coverage matte
            rgba_matte = d.merge_matte_and_rgb(id_matte, beauty_img)

            # Pre-multiply RGBA matte
            rgba_matte = self.img_util.premultiply_image(rgba_matte)
            matte_img_file = self.output_dir / f'{create_file_safe_name(layer_name)}.{self.cryptomatte_out_file_ext}'

            # Create image file dict entry
            img_file_dict.update({matte_img_file.stem: dict(path=matte_img_file, processed=True)})
            # Create image
            self.img_util.write_image(matte_img_file, rgba_matte)

        # CleanUp
        d.shutdown()
        try:
            del d
        except Exception as e:
            LOGGER.error(e)

        return img_file_dict, img_file_dict
