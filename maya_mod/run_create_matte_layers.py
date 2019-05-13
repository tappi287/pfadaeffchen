#! usr/bin/python_2
"""
    Maya script to create foreground and background matte render layer

    Provide a mayapy executable with this script and command line arguments
    mayapy.exe "path_to_this_script" "path_to_csb_or_mb"
    mayapy.exe "./my_script.py" "C:/maya_dir/ifile.mb"


    MIT License

    Copyright (c) 2018 Stefan Tapper

    Permission is hereby granted, free of charge, to any person obtaining a copy
    of this software and associated documentation files (the "Software"), to deal
    in the Software without restriction, including without limitation the rights
    to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
    copies of the Software, and to permit persons to whom the Software is
    furnished to do so, subject to the following conditions:

    The above copyright notice and this permission notice shall be included in all
    copies or substantial portions of the Software.

    THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
    IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
    FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
    AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
    LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
    OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
    SOFTWARE.
"""

# Initialize a Maya session without GUI
import maya.standalone
maya.standalone.initialize()

# From here on we are executed in a Maya session
import os
import sys
import argparse

# Define command line arguments
parser = argparse.ArgumentParser()
# Positional argument 1 file_path
parser.add_argument('file_path', help='Absolute path to the CSB file or MB file to import.', type=str)
parser.add_argument('render_path', help='Absolute path to the render output directory', type=str)
parser.add_argument('env', help='Space separated, quoted Paths to extend the mayapy pythonpaths.', type=str)
parser.add_argument('version', help='String value 2016.5 or 2017', type=str)
parser.add_argument('renderer', help='String value eg. mayaHardware2', type=str)
parser.add_argument('csb_ignore_hidden', help='Boolean as integer 1 or 0', type=int)
parser.add_argument('maya_delete_hidden', help='Boolean as integer 1 or 0', type=int)

# Parse command line arguments
args = parser.parse_args()
if args.env:
    for env_path in args.env.split(' '):
        if env_path not in sys.path:
            __msg = 'Extending sys path: ' + env_path
            print(__msg)
            sys.path.append(env_path)

# Import pymel to initialise mayapy
import pymel.core as pm
import maya_mod.maya_matte_layers as maya_matte_layers
import maya_mod.maya_render_settings as maya_render_settings
from maya_mod.maya_tappitilitys import MayaFileUtils as mfu, load_csb_plugin, load_mtoa_plugin, MayaUtils as mu, \
    create_arnold_default_light
from modules.setup_log import setup_logging
from maya_mod.socket_client import send_message

LOGGER = setup_logging(__name__)
LOGGER.info('Running create matte layers in Maya Standalone with args:\n%s', args)


def main():
    LOGGER.debug('Running in batch: %s', pm.about(batch=True))

    # Prepare file paths
    base_dir = os.path.dirname(args.file_path)
    scene_name = os.path.splitext(os.path.basename(args.file_path))[0]
    scene_ext = os.path.splitext(args.file_path)[1]
    render_scene_name = scene_name + '_render.mb'
    render_scene_file = os.path.join(base_dir, render_scene_name)

    # Set rendering path
    img_path = os.path.abspath(args.render_path)

    # Create rendering dir
    if not os.path.exists(img_path):
        try:
            os.mkdir(img_path)
            send_message('Erstelle Ausgabe Verzeichnis:<i>' + os.path.split(img_path)[-1] + '</i>')
        except Exception as e:
            LOGGER.error(e)

    # --- Prepare CSB import
    if scene_ext.capitalize() == '.csb':
        if not load_csb_plugin(args.version):
            LOGGER.fatal('Could not load rttDirectMayaPlugIn. Can not import CSB files. Aborting batch process.')
            send_message('Konnte rttDirectMayaPlugIn nicht laden. Vorgang abgebrochen.')
            return

    # --- Prepare Arnold Renderer PlugIn
    if args.renderer == 'arnold':
        if not load_mtoa_plugin():
            LOGGER.fatal('Could not load mtoa. Can not render using arnold. Aborting batch process.')
            send_message('Konnte Arnold Renderer nicht laden. Vorgang abgebrochen.')
            return

    # Open or import file
    if scene_ext.capitalize() == '.csb':
        # Import CSB File
        send_message('Importiere CSB Szenendatei:<br><i>' + scene_name + '</i>')
        send_message('COMMAND STATUS_NAME Importiere CSB Datei')
        mfu.import_csb(args.file_path, args.csb_ignore_hidden)
    elif scene_ext.capitalize() == '.mb':
        # Load maya binary
        send_message('Oeffne Maya Binaere Szenendatei:<br><i>' + scene_name + '</i>')
        send_message('COMMAND STATUS_NAME Importiere Maya Binary')
        mfu.open_file(args.file_path)

    # Check for DeltaGen camera "Camera"
    if not mu.get_camera_by_name('Camera'):
        send_message('Keine renderbare Kamera - "Camera" gefunden! Vorgang abgebrochen.')
        LOGGER.fatal('Renderable Camera with exact name "Camera" could not be found. Aborting layer creation.')
        return

    # Setup scene with foreground matte layers per material
    send_message('Erstelle render layer setup.')
    send_message('COMMAND STATUS_NAME Erstelle Render-Layer Setup')
    num_layers = maya_matte_layers.create(maya_delete_hidden=args.maya_delete_hidden,
                                          renderer=args.renderer)
    send_message('{:04d} Layer erstellt.'.format(num_layers))
    send_message('COMMAND LAYER_NUM {:04d}'.format(num_layers))

    # Setup render settings
    send_message('Setze ' + args.renderer + ' Einstellungen.')
    maya_render_settings.setup_render_settings('Camera', img_path, args.env, args.renderer)

    # Save the scene
    mfu.save_file(render_scene_file)
    send_message('Rendering Szenendatei erstellt:<br><i>' + render_scene_file + '</i>')

    # Close the scene
    mfu.new_file()
    send_message('Szene entladen. Ressourcen freigegeben.')
    send_message('COMMAND STATUS_NAME Rendering Szene erstellt')


if __name__ == '__main__':
    main()
