#! usr/bin/python_2
"""
    Maya script to create foreground and background matte render layer

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

import maya.api.OpenMaya as Om
import maya.app.renderSetup.model.renderSetup as renderSetup
import logging
from maya.app.renderSetup.model import typeIDs

from .mrShadersToArnold import convertAllShaders
from . import maya_tappitilitys
from . import maya_render_settings
from . import maya_delete
from modules.setup_log import setup_logging

LOGGER = setup_logging(__name__)

maya_useNewAPI = True


class MayaMatteLayer(object):
    """
        Create matte layer with renderSetup.
        Foreground objects get a surfaceShader override,
        Background objects will be collected and opionally
        override with useBackgroundShader

        Requires a renderSetup instance on init
    """
    fg_collection_name = 'fg_collection'
    fg_override_name = 'fg_override'

    bg_collection_name = 'bg_collection'
    bg_override_name = 'bg_override'

    layer_name_suffix = 'pfad'

    def __init__(self, rs):
        mu = maya_tappitilitys.MayaUtils
        self.mu = mu
        self.rs = rs

        # Private Property variables
        self.__render_layer = list()
        self.__layer_count = 0

        self.fg_collection_count = 0
        self.bg_collection_count = 0

        # Prepare background and path materials
        self.bg_shader, self.bg_shading_grp = mu.create_material('useBackground')
        LOGGER.debug('Background Shading Group: %s', self.bg_shading_grp.name())
        self.fg_shader, self.fg_shading_grp = mu.create_material('lambert')
        LOGGER.debug('Foreground Shading Group: %s', self.fg_shading_grp.name())

    @property
    def render_layer(self):
        return self.__render_layer

    @render_layer.setter
    def render_layer(self, val):
        self.__render_layer.append(val)

    @render_layer.deleter
    def render_layer(self):
        self.__render_layer = list()

    @staticmethod
    def count(c, pre='_', suf=''):
        return '{}{:03d}{}'.format(pre, c, suf)

    def create_layer(self, name):
        self.__layer_count += 1
        name = name + self.count(self.__layer_count) + '_' + self.layer_name_suffix

        __rl = self.rs.createRenderLayer(name)
        self.render_layer = __rl
        return __rl

    def create_fg_collection(self, render_layer):
        """
            Create a foreground collection and apply a
            surface Shader as override to matte objects.
        """
        self.fg_collection_count += 1
        __c = self.count(self.fg_collection_count)

        __ovr_name = self.fg_override_name + __c
        __name = self.fg_collection_name + __c

        # Create collection
        __rc = render_layer.createCollection(__name)

        # Create matte Material override
        self.create_material_override(__rc,
                                      self.fg_shading_grp.name(),
                                      __ovr_name)

        return __rc

    def create_bg_collection(self, render_layer, create_override=False):
        """
            Create a background collection for all objects that mask matte objects.
        """
        self.bg_collection_count += 1
        __c = self.count(self.bg_collection_count)

        __name = self.bg_collection_name + __c
        __ovr_name = self.bg_override_name + __c

        # Create collection
        __rc = render_layer.createCollection(__name)

        # Add all transform nodes to collection
        __rc.getSelector().setPattern('*')

        # Create background Material override
        if create_override:
            self.create_material_override(__rc,
                                          self.bg_shading_grp.name(),
                                          __ovr_name)

        return __rc

    def assign_background_to_scene(self):
        """ Assigns the background shader to the entire scene! """
        self.mu.assign_material_to_scene(self.bg_shading_grp)

    @staticmethod
    def create_material_override(collection, shading_group, name):
        """
            Creates a material override for the provided collection and
            assigns it to the provided shadingEngine.

            Do not forget to provide me with a unique name.
        """
        # Create material override
        __ovr = collection.createOverride(name, typeIDs.materialOverride)

        # Connect shadingEngine to override
        try:
            # Maya 2017 Update 4
            __ovr.setOverrideConnection(shading_group + '.message', applyIt=True)
        except Exception as e:
            # Pre Maya 2017 Update 4
            # 2017 Update 3 also has a setMaterial method
            LOGGER.debug(e)
            __ovr.setSource(shading_group + '.message')

        return __ovr


def create(maya_delete_hidden=1, renderer='mayaSoftware', use_scene_settings=0):
    # Delete all hidden objects
    try:
        if maya_delete_hidden:
            maya_delete.hidden_objects()
    except Exception as e:
        LOGGER.error(e)

    # Delete empty groups
    try:
        maya_delete.empty_groups()
    except Exception as e:
        LOGGER.error(e)

    # Delete all lights
    try:
        if not use_scene_settings:
            maya_delete.all_lights()
    except Exception as e:
        LOGGER.error(e)

    if renderer == 'arnold':
        if not use_scene_settings:
            maya_tappitilitys.create_arnold_default_light()

        # Make sure shadingGroups contain only ASCII characters
        # otherwise AOV creation may fail
        maya_tappitilitys.MayaUtils.rename_shading_grps_to_ascii()

        # Convert all materials to ai_standard shader
        log_level = LOGGER.getEffectiveLevel()
        logging.root.setLevel(logging.ERROR)
        try:
            convertAllShaders()
        except Exception as e:
            LOGGER.error('Shader conversion failed with error: %s', e)
        logging.root.setLevel(log_level)

        """
            Skip render layer setup, we will use cryptomatte crypto_material AOV with arnold
            Return 10 as number of layers so we can update batch render status in 10% steps
        """
        return 10

    # Create RenderSetup instance
    rs = renderSetup.instance()

    # Shortcut to our Utility class
    mu = maya_tappitilitys.MayaUtils

    # Assign material to corrupted objects which lost there shading group during clean-up
    _, shading_grp = mu.create_material('blinn', color=(1.0, 0.0, 0.0))
    mu.assign_to_objects_without_shading_group(shading_grp)

    # Get all shadingGroups of the scene which are connected to meshes
    shading_groups = mu.get_scene_shading_groups()

    # Setup Helper Class
    matte_layer = MayaMatteLayer(rs)

    for __s in shading_groups:
        # Get material name
        material_name = mu.get_shader_name(__s)

        # Create render layer for shading group
        rl = matte_layer.create_layer(material_name)

        """
        Skip background collections material override this time as it is way too slow when rendering.
        We simply apply a background shader to the entire scene and only override
        the foreground objects.
        """
        # Create collections for foreground und background objects
        matte_layer.create_bg_collection(rl, create_override=False)
        matte_collection = matte_layer.create_fg_collection(rl)

        # LOGGER.debug messages
        LOGGER.debug('---------------------------------------------------')
        LOGGER.debug('Shading Group: %s', Om.MFnDependencyNode(__s).name())
        LOGGER.debug('Material Name: %s', material_name)
        LOGGER.debug('Objects with Material:')

        __log_name_list = list()
        # Iterate transform nodes of shading group
        for __o in mu.get_objects_of_shading_group(__s):
            __name = __o.name()

            # Adding full DAG path's of all instances(getAllPaths) to selector
            if __name:
                matte_collection.getSelector().staticSelection.add(__o.getAllPaths())
                __log_name_list.append(__name)

        LOGGER.debug('%s\n\n', __log_name_list)

    # Apply background shader to entire scene
    # because creating a wildcard collection for every renderLayer
    # is fast when setting up. But it is painfully slow when rendering.
    matte_layer.assign_background_to_scene()

    return len(matte_layer.render_layer)
