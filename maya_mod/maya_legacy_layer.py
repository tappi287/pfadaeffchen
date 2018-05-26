#! usr/bin/python_2
"""
    Obsolete modules to create legacy Maya render layers

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
import maya.cmds as cmds
from maya.OpenMaya import MGlobal


class MayaUtility(object):
    """
        Utility class to perform common Maya scene tasks

        This is a static class. Do not instantiate it.
    """
    @staticmethod
    def print_maya(str_to_print):
        """ Print to Maya Script Editor as python comment """
        MGlobal.displayInfo(str_to_print)

    @staticmethod
    def get_objects_of_materials(materials):
        """
        Return mesh objects of materials
        :param materials: list of materials
        :return: list of mesh objects
        """
        cmds.select(materials)
        cmds.hyperShade(objects='')

        return cmds.ls(selection=True)

    @staticmethod
    def get_root_materials(include_unused=False):
        """ Returns a sorted list of root materials in the current scene """
        root_materials = []

        for current in cmds.ls(type='shadingEngine', long=True):
            shader = cmds.listConnections(current + '.surfaceShader', source=True, destination=False)

            if not shader:
                MayaUtility.print_maya('WARNING: Shading group ' + current + ' has no surface shader')
                continue

            if include_unused:
                if shader[0] not in root_materials:
                    root_materials.append(shader[0])
            else:
                if cmds.sets(current, query=True):
                    if shader[0] not in root_materials:
                        root_materials.append(shader[0])

        root_materials.sort()

        return root_materials

    @staticmethod
    def get_root_items():
        """
        Return all root transform nodes of the scene excluding cameras
        :return: root_items: list of transform nodes
        """
        nodes = cmds.ls(dag=True, type='transform', visible=True)
        root_items = list()

        if not nodes:
            return None

        for n in nodes:
            # Get parent transform node
            parent = cmds.listRelatives(n, parent=True, type='transform')

            # Get root items without parent
            if not parent:

                # Filter camera nodes
                cam = cmds.listRelatives(n, type='camera')
                if not cam:
                    root_items.append(n)

        return root_items

    @staticmethod
    def set_attr_in_layer(attr=None, layer=None, value=None):
        """
        Same as cmds.setAttr but this sets the attribute's value in a given render layer without having to switch to it
        :param attr: string - ex: "node.attribute"
        :param layer: string - ex: "layer_name"
        :param value: value you want to set the override to
        :return: bool - True if successful, False if not
        """
        cmds.editRenderLayerAdjustment(attr, layer=layer)

        connection_list = cmds.listConnections(attr, plugs=True)

        if connection_list is not None:
            for connection in connection_list:
                attr_component_list = connection.split(".")

                if attr_component_list[0] == layer:
                    attr = ".".join(attr_component_list[0:-1])
                    cmds.setAttr("%s.value" % attr, value)
                    return True

        return False

    @staticmethod
    def get_attr_in_layer(attr=None, layer=None):
        """
        Same as cmds.getAttr but this gets the attribute's value in a given render layer without having to switch to it
        :param attr: string - ex: "node.attribute"
        :param layer: string - ex: "layer_name"
        :return: multi - can return any objects
        """
        connection_list = cmds.listConnections(attr, plugs=True)

        if connection_list is None:
            return cmds.getAttr(attr)

        for connection in connection_list:
            attr_component_list = connection.split(".")

            if attr_component_list[0] == layer:
                attr = ".".join(attr_component_list[0:-1])
                MayaUtility.print_maya(attr)
                return cmds.getAttr("%s.value" % attr)

        return cmds.getAttr(attr)

    @staticmethod
    def clear_render_layer():
        """ Clear all render layer except masterLayer """
        for rl in cmds.ls(type='renderLayer'):
            if rl != 'masterLayer':
                cmds.delete(rl)


class CreateLegacyRenderLayers:
    def __init__(self):
        # Shortcut to Maya utility class
        self.mu = MayaUtility

        # Set of created render layers
        self.rl = set()

        # List of all mesh objects
        self.all_obj = cmds.ls(dag=True, type='mesh')

    def create_per_material(self):
        """ Create a render layer per material """
        # Collect root items
        root_items = self.mu.get_root_items()

        if not root_items:
            self.mu.print_maya('No root items found, scene empty?')
            return

        # Collect root materials
        materials = self.mu.get_root_materials()

        if not materials:
            self.mu.print_maya('No materials found, scene empty?')
            return

        for __m in materials:
            # Create Layer
            layer = self.create_layer(root_items, __m)

            # Set all objects to Hold Out
            self.set_hold_out_layer_override(layer=layer, value=1)

            # Select objects with current material
            material_objects = self.mu.get_objects_of_materials([__m])

            # Remove Hold out from material's objects
            if material_objects:
                self.set_hold_out_layer_override(material_objects, layer, 0)
            else:
                cmds.delete(layer)

            self.rl.add(layer)

    def create_layer(self, root_items, name='pfad_layer'):
        """ Create layer and include all root/all objects """
        # name_001
        name = '{0}_{1:03d}'.format(name, len(self.rl))

        # Create render layer, noRecurse->add all child objects of root obj
        __rl = cmds.createRenderLayer(root_items, noRecurse=False, name=name)

        return __rl

    def set_hold_out_layer_override(self, nodes=None, layer=None, value=1):
        """ Set holdOut attribute for nodes to value """
        if nodes is None:
            nodes = self.all_obj

        for __n in nodes:
            self.mu.set_attr_in_layer(__n + '.holdOut', layer, value)


def main():
    create_render_layer = CreateLegacyRenderLayers()
    create_render_layer.create_per_material()


if __name__ == '__main__':
    main()