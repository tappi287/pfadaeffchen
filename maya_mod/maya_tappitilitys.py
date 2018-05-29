#! usr/bin/python_2
"""
    Generic Maya Utilities

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
import maya.api.OpenMaya as Om
import maya.api.OpenMayaUI as OmUi
import maya.cmds as cmds
import maya.mel as mel
from modules.setup_log import setup_logging
from modules.setup_paths import get_maya_version

LOGGER = setup_logging(__name__)

def maya_useNewAPI():
    pass


# Load Maya Tappitilitys settings
current_dir = os.path.dirname(__file__)
settings_dir = os.path.join(current_dir, '../res/mt_settings.json')
settings_dir = os.path.abspath(settings_dir)

with open(settings_dir, 'r') as f:
    mt_settings = json.load(f, encoding="utf-8")


def load_csb_plugin(version, csb_plugin_loaded=None):
    """ Make sure we can import csb """

    # Check loaded PlugIns
    loaded_plugins = cmds.pluginInfo(listPlugins=True, q=True)
    LOGGER.debug('Maya PlugIns loaded:\n%s', loaded_plugins)

    if version:
        maya_version = version
    else:
        maya_version = get_maya_version()

    plugin_dict = {
                   '2017': 'rttDirectMayaPlugIn2017',
                   '2016.5': 'rttDirectMayaPlugIn2016_5',
                   '2016': 'rttDirectMayaPlugIn2016'
                   }

    # Try to load the appropriate plugin for current Maya version
    if maya_version:
        if plugin_dict[maya_version] in loaded_plugins:
            # PlugIn already loaded
            return True
        else:
            # Try to load plugIn
            csb_plugin_loaded = cmds.loadPlugin(plugin_dict[maya_version])

            if csb_plugin_loaded:
                return True

    # Plugin load unsuccessful, iterate remaining options
    for __csb_plugin in plugin_dict.values():
        if __csb_plugin in loaded_plugins:
            return True

    while plugin_dict:
        _, __csb_plugin = plugin_dict.popitem()

        try:
            csb_plugin_loaded = cmds.loadPlugin(__csb_plugin)
        except Exception as e:
            LOGGER.error(e)

        if csb_plugin_loaded:
            return True

    return False


class MayaBaseUtils(object):
    """ Basic lower level utilities """

    @staticmethod
    def dag_iterator(traversal_type=Om.MItDag.kBreadthFirst, filter_type=Om.MFn.kTransform):
        """
        Iterate DAG objects as generator

        :param traversal_type:
        :type traversal_type: int
        :param filter_type:
        :type filter_type: int
        :rtype: generator[Om.MObject]
        :return: MObject
        """

        dag_iter = Om.MItDag(traversalType=traversal_type, filterType=filter_type)

        # Iterate DAG tree
        while not dag_iter.isDone():
            # Get current item
            __i = dag_iter.currentItem()

            # Break on invalid item
            if __i.isNull():
                break

            dag_iter.next()

            yield __i

    @staticmethod
    def get_connections(m_object):
        """ Return plugs of m_object """
        dp = Om.MFnDependencyNode(m_object)
        plugs = dp.getConnections()

        for __n in plugs:
            yield __n

    @staticmethod
    def get_attr_connections(plug, as_dest=False, as_src=True):
        """
        Return attribute connections of plug
        :param plug:
        :type plug: Om.MPlug
        :param as_dest: list connections this plug is the destination of
        :param as_src: list connections this plug is the source of
        :return: connection as generator
        :rtype: generator Om.
        """

        connections = plug.connectedTo(as_dest, as_src)

        for __c in connections:
            yield __c

    @staticmethod
    def find_object_plug(m_obj, plug_name):
        __m = Om.MFnDependencyNode(m_obj)

        try:
            __m_plug = __m.findPlug(plug_name, False)
        except Exception as e:
            LOGGER.debug(e)
            return None

        return __m_plug

    @staticmethod
    def set_plug_bool(m_plug, value=False):
        try:
            m_plug.setBool(value)
        except Exception as e:
            LOGGER.debug(e)
            return False

        return True

    @staticmethod
    def find_object_by_name(name):
        selection_list = Om.MSelectionList()

        try:
            selection_list.add(name)
        except Exception as e:
            LOGGER.error('Error finding : %s Exception:\n%s', name, e)
            return None

        try:
            __m_object = selection_list.getDependNode(0)
        except Exception as e:
            LOGGER.error('Error finding depend node of: %s Exception:\n%s', name, e)
            return None

        return Om.MFnDependencyNode(__m_object)

    @staticmethod
    def find_dag_path_by_name(name):
        selection_list = Om.MSelectionList()

        try:
            selection_list.add(name)
        except Exception as e:
            LOGGER.error('Error finding Dag Path: %s Exception:\n%s', name, e)
            return None

        try:
            __dag_path = selection_list.getDagPath(0)
        except Exception as e:
            LOGGER.error('Error finding Dag Path: %s Exception:\n%s', name, e)
            return None

        return Om.MDagPath(__dag_path)


class MayaUtils(object):
    """
        Utility class to perform common Maya scene tasks, in Maya Python API 2.0
    """

    @staticmethod
    def get_version():
        """ Returns 2016 / 2017 etc. """
        version = cmds.about(version=True)

        if version not in mt_settings['valid_maya_versions']:
            if version:
                LOGGER.warning('Unsupported Maya version %s detected.', version)

        if not version:
            return '2017'

        return version

    @staticmethod
    def dag_iterate_objects(traversal_type=Om.MItDag.kBreadthFirst, filter_type=Om.MFn.kTransform,
                            object_type=Om.MFnTransform, __t=None):
        """
        Iterates DAG and returns object of specified object_type as generator
        :param traversal_type:
        :param filter_type:
        :param object_type:
        :param __t:
        :return: object as object_type
        """
        mbu = MayaBaseUtils

        for __i in mbu.dag_iterator(traversal_type, filter_type):
            # Check item type
            if __i.hasFn(filter_type):
                __t = object_type(__i)

                yield __t

    @staticmethod
    def get_root_transforms(get_cameras=False):
        """ Returns the scene root transform nodes excluding cameras """
        __nodes = list()

        for node in MayaUtils.dag_iterate_objects(traversal_type=Om.MItDag.kBreadthFirst):
            if node.parentCount():
                __parent = Om.MFnDagNode(node.parent(0)).name()

                # Children of the world
                if __parent == 'world':
                    # Make sure we have a valid child index
                    if node.childCount() > 0:
                        # Not a camera transform node
                        if not node.child(0).hasFn(Om.MFn.kCamera) and not get_cameras:
                            __nodes.append(node)
                        # Collect Cameras
                        elif node.child(0).hasFn(Om.MFn.kCamera) and get_cameras:
                            __nodes.append(node)
                else:
                    # Important - Works only with traversal type breadth first!
                    break

        return __nodes

    @staticmethod
    def get_object_attr_conn(m_object, as_dest=False, as_src=True):
        """
        Returns attribute connections as generator Om.MPlug
        :param m_object:
        :type m_object: Om.MObject
        :param as_dest: list connections this plug is the destination of
        :type as_dest: bool
        :param as_src: list connections this plug is the source of
        :type as_src: bool
        :return: Attribute connections of m_object
        :rtype: generator[Om.MPlug]
        """
        mbu = MayaBaseUtils

        for __a in mbu.get_connections(m_object):
            for __c in mbu.get_attr_connections(__a, as_dest, as_src):
                yield __c

    @staticmethod
    def get_instances():
        dag_iter = Om.MItDag(traversalType=Om.MItDag.kDepthFirst, filterType=Om.MFn.kTransform)
        __instances = list()

        while not dag_iter.isDone():
            instanced = dag_iter.isInstanced()

            if instanced:
                __instances.append(dag_iter.fullPathName())

            dag_iter.next()

        return __instances

    @staticmethod
    def find_dag_path_by_name(name):
        mbu = MayaBaseUtils

        return mbu.find_dag_path_by_name(name)

    @staticmethod
    def get_shader_name(m_object):
        """ Get surface shader name of shading group """
        mbu = MayaBaseUtils
        name = None

        try:
            shader_plug = mbu.find_object_plug(m_object, 'surfaceShader')
        except Exception as e:
            LOGGER.debug(e)
            return None

        if not shader_plug:
            return None

        for __m in mbu.get_attr_connections(shader_plug, True, False):
            if __m:
                material = Om.MFnDependencyNode(__m.node())
                name = material.name()

        return name

    @classmethod
    def uninstance_scene(cls):
        """ Way too slow for big scenes, do not use """
        instances = cls.get_instances()

        while instances:
            parent = cmds.listRelatives(instances[0], parent=True, fullPath=True)[0]
            cmds.duplicate(parent, renameChildren=True)
            cmds.delete(parent)
            instances = cls.get_instances()

    @classmethod
    def get_scene_shading_groups(cls):
        """ Return all shading groups connected to mesh geometry as Om.MObjectArray """
        mbu = MayaBaseUtils

        shading_groups = Om.MObjectArray()

        for __t in mbu.dag_iterator(filter_type=Om.MFn.kMesh):
            for __a in cls.get_object_attr_conn(__t, False, True):
                __a = __a.node()
                if __a.hasFn(Om.MFn.kShadingEngine):
                    if __a not in shading_groups:
                        shading_groups.append(__a)

        return shading_groups

    @classmethod
    def get_objects_of_shading_group(cls, shading_group):
        """ Returns Transform nodes connected to shading group """

        # Get connections
        for __s in cls.get_object_attr_conn(shading_group, True, False):
            # Connected to mesh
            if __s.node().hasFn(Om.MFn.kMesh):
                # Get DagNode
                __m = Om.MFnDagNode(__s.node())

                # Traverse to parent(Transform node)
                __m = __m.parent(0)

                if not __m.isNull():
                    __m = Om.MFnDagNode(__m)
                    # Return Transform node
                    yield __m

    @classmethod
    def assign_to_objects_without_shading_group(cls, shading_engine):
        """ Find meshes not in a shadingGroup and assign the provided shading engine to them """
        mbu = MayaBaseUtils
        meshes_without_shading = list()

        for __t in mbu.dag_iterator(filter_type=Om.MFn.kMesh):
            has_shading = False
            for __a in cls.get_object_attr_conn(__t, False, True):
                __a = __a.node()

                if __a.hasFn(Om.MFn.kShadingEngine):
                    has_shading = True
                    continue

            if not has_shading:
                __t = Om.MFnDagNode(__t)
                print(__t.getPath().fullPathName())
                meshes_without_shading.append(__t.getPath().fullPathName())

        # Get name of shading group
        shading_grp_name = shading_engine.name()

        # Force assign shadingEngine to objects with maya.cmds
        cmds.sets(meshes_without_shading, forceElement=shading_grp_name, noWarnings=True)

    @staticmethod
    def create_material(material_type='lambert', color=(1.0, 1.0, 1.0)):
        """
        Creates material of specified material_type and returns tuple with shader node and shading group node
        :param material_type: ['lambert' | 'blinn' | 'surfaceShader' | 'useBackground']
        :param color: shader.color as (float, float, float)
        :return: (shading_node, shading_group)
        :rtype (Om.MFnDagNode, Om.MFnDagNode):
        """
        mbu = MayaBaseUtils

        # create a shader
        shader = cmds.shadingNode(material_type, asShader=True)
        try:
            cmds.setAttr((shader + '.color'), color[0], color[1], color[2], type='double3')
        except:
            pass

        try:
            cmds.setAttr((shader + '.outColor'), color[0], color[1], color[2], type='double3')
        except:
            pass

        # a shading group
        shading_group = cmds.sets(renderable=True, noSurfaceShader=True, empty=True)

        # connect shader to sg surface shader
        cmds.connectAttr('%s.outColor' % shader, '%s.surfaceShader' % shading_group)

        material_node = mbu.find_object_by_name(shader)
        shading_group_node = mbu.find_object_by_name(shading_group)

        return material_node, shading_group_node

    @classmethod
    def assign_material_to_scene(cls, shading_engine):
        """ Assign a material to the entire scene """

        # Get root transform nodes
        __root_transforms = cls.get_root_transforms()

        # Convert to list of names
        obj_ls = list()
        for __n in __root_transforms:
            __n = Om.MFnDagNode(__n.object())
            obj_ls.append(__n.getPath().fullPathName())

        # Get name of shading group
        shading_grp_name = shading_engine.name()

        LOGGER.info('Assigning shader to %s', obj_ls)

        # Force assign shadingEngine to objects with maya.cmds
        cmds.sets(obj_ls, forceElement=shading_grp_name, noWarnings=True)

    @classmethod
    def get_camera_by_name(cls, camera_name):
        for c in cls.get_root_transforms(get_cameras=True):
            if c.name() == camera_name:
                camera_dag_obj = Om.MFnDagNode(c)
                break
        else:
            camera_dag_obj = None

        return camera_dag_obj

    @staticmethod
    def set_viewport_camera(camera):
        viewport = OmUi.M3dView.active3dView()
        viewport.setCamera(camera)

    @classmethod
    def set_renderable_camera(cls, camera_name):
        """ Set all cameras un-renderable except camera matching camera_name """
        mbu = MayaBaseUtils
        __camera_found = False
        __successfully_set = False

        for c in cls.get_root_transforms(get_cameras=True):
            # Get camera shape as MObject
            __m_obj = c.child(0)

            # Get renderable plug
            __plug = mbu.find_object_plug(__m_obj, 'renderable')

            # Set camera plug renderable true or false
            if c.name() == camera_name and __plug:
                # Found render camera, set renderable
                __camera_found = mbu.set_plug_bool(__plug, True)
                __successfully_set = __camera_found
            elif __plug:
                # Not the render camera, set to not renderable
                __successfully_set = mbu.set_plug_bool(__plug, False)

        if __camera_found and __successfully_set:
            # Camera found and successfully set renderable attributes
            return True

        # Camera not found or error while setting renderable attribute
        return False

    @staticmethod
    def unlock_renderer(renderer="mayaHardware2"):
        LOGGER.debug("Unlocking and resetting current renderer")

        # Unlock the render globals' current renderer attribute
        cmds.setAttr("defaultRenderGlobals.currentRenderer", l=False)

        # Sets the current renderer to given renderer
        cmds.setAttr("defaultRenderGlobals.currentRenderer", renderer, type="string")

    @staticmethod
    def remake_render_settings_ui(renderer="mayaSoftware"):
        """ Remakes the render settings window """
        # Unlock the render globals' current renderer attribute
        cmds.setAttr("defaultRenderGlobals.currentRenderer", l=False)

        # Sets the current renderer to given renderer
        cmds.setAttr("defaultRenderGlobals.currentRenderer", renderer, type="string")

        # Deletes the render settings window UI completely
        if cmds.window("unifiedRenderGlobalsWindow", exists=True):
            cmds.deleteUI("unifiedRenderGlobalsWindow")

        # Remake the render settings UI
        mel.eval('unifiedRenderGlobalsWindow;')


class MayaFileUtils(object):
    @staticmethod
    def import_csb(file_path, ignore_hidden_objects=1):
        file_type = mt_settings['csb_import']['typ']
        options = mt_settings['csb_import']['options']

        # Set ignoreHiddenObject option
        search = 'ignoreHiddenObject='
        if search in options:
            s = options.find(search)
            e = s + len(search) + 1
            option_str = options[s:e]
            new_option_str = option_str[:-1] + str(ignore_hidden_objects)

            # Set option by replacing the option string
            options = options.replace(option_str, new_option_str)

        cmds.file(file_path, i=True, typ=file_type, options=options)

    @staticmethod
    def open_file(file_path):
        cmds.file(file_path, open=True, ignoreVersion=True, prompt=False, force=True)

    @staticmethod
    def save_file(file_path, file_type='mayaBinary'):
        cmds.file(rename=file_path)
        cmds.file(save=True, typ=file_type)

    @staticmethod
    def new_file():
        """ Close the current scene and create a new scene """
        cmds.file(newFile=True, prompt=False, force=True)

    @staticmethod
    def set_images_dir(dir, rule='images'):
        """ Set project output directory """
        if not os.path.exists(dir):
            try:
                os.mkdir(dir)
            except Exception as e:
                LOGGER.debug(e)
                return False

        cmds.workspace(fileRule=[rule, dir])
        return True
