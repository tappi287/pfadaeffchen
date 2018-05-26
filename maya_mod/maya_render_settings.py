#! usr/bin/python_2
"""
    JSON partly import stolen from:
    http://around-the-corner.typepad.com/adn/2017/01/how-to-importexport-render-setup-with-python.html

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
import os
import json
import maya.app.renderSetup.model.renderSetup as renderSetup
import maya.app.renderSetup.model.renderSettings as renderSettings

from maya import cmds as cmds, mel as mel
from maya_mod.maya_tappitilitys import MayaUtils as mu, MayaFileUtils as mfu
from modules.setup_log import setup_logging
LOGGER = setup_logging(__name__)


def importRenderSetup(filename):
    with open(filename, "r") as file:
        renderSetup.instance().decode(json.load(file), renderSetup.DECODE_AND_OVERWRITE, None)


def exportRenderSetup(filename, note=None):
    with open(filename, "w+") as file:
        json.dump(renderSetup.instance().encode(note), fp=file, indent=2, sort_keys=True)


# Additional load renderSettings
def importRenderSettings(filename):
    with open(filename, 'r') as file:
        renderSettings.decode(json.load(file))


def setup_sw():
    """
        Alternative to renderSetup settings import set render globals manually
    """
    mu.unlock_renderer('mayaSoftware')
    mel.eval('loadPreferredRenderGlobalsPreset("mayaSoftware");')
    mel.eval('mayaHasRenderSetup;')

    cmds.setAttr("defaultRenderQuality.edgeAntiAliasing", 0)

    cmds.setAttr("defaultRenderQuality.shadingSamples", 2)
    cmds.setAttr("defaultRenderQuality.maxShadingSamples", 8)

    cmds.setAttr("defaultRenderQuality.useMultiPixelFilter", 1)
    cmds.setAttr("defaultRenderQuality.pixelFilterType", 5)
    cmds.setAttr("defaultRenderQuality.pixelFilterWidthX", 1.5)
    cmds.setAttr("defaultRenderQuality.pixelFilterWidthY", 1.5)


def setup_hw2():
    """
        Alternative to renderSetup settings import set render globals manually
    """
    cmds.hwRenderLoad()

    # Unlock and set required renderer
    # Loading renderSettings should set the renderer but fails depending
    # on the Maya version
    mu.unlock_renderer('mayaHardware2')
    mel.eval('loadPreferredRenderGlobalsPreset("mayaHardware2");')
    mel.eval('mayaHasRenderSetup;')
    cmds.setAttr('hardwareRenderingGlobals.multiSampleEnable', 1)
    cmds.setAttr('hardwareRenderingGlobals.multiSampleCount', 16)


def setup_render_settings(render_camera='Camera', img_path='', env='.', renderer=''):
    """ Setup the renderer and render settings """

    if renderer == 'mayaSoftware':
        # Setup mayaSoftware renderer
        settings_path = os.path.join(env, 'res/renderSettings_sw.json')

        setup_sw()
    else:
        # Setup mayaHardware2 renderer
        settings_path = os.path.join(env, 'res/renderSettings.json')

        setup_hw2()

    # Load -our- default render setup settings
    try:
        importRenderSettings(settings_path)
    except Exception as e:
        LOGGER.error('Failed to import renderSetup render settings: %s', e)

    # Set the rendering camera
    if not mu.set_renderable_camera(render_camera):
        LOGGER.error('Could not set render camera: %s', render_camera)

    # Set rendering path
    mfu.set_images_dir(img_path)
