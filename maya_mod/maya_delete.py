#! usr/bin/python_2
"""
    Utility to delete types of objects from a Maya scene

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
import pymel.core as pm
import re
from modules.setup_log import setup_logging

LOGGER = setup_logging(__name__)

maya_useNewAPI = True


def dag_path_iterator(traversal_type=Om.MItDag.kBreadthFirst, filter_type=Om.MFn.kTransform):
    dag_iter = Om.MItDag(traversalType=traversal_type, filterType=filter_type)

    # Iterate DAG tree
    while not dag_iter.isDone():
        # Get current item
        __p = dag_iter.getPath()

        # Break on invalid item
        if dag_iter.currentItem().isNull():
            break

        dag_iter.next()

        yield __p


def delete(dag_path_array):
    """ Delete MFnDagNode or list of MFnDagNode's or set of dag path string's """
    objects_to_delete = list()

    for dag_path in dag_path_array:
        objects_to_delete.append(dag_path.fullPathName())

    try:
        pm.delete(objects_to_delete)
    except Exception as e:
        LOGGER.error(e)


def hidden_objects():
    """ Removes all invisible objects from a scene """
    # TODO: Deletes/unconnects shading groups from instanced instances
    # eg, Screws shared by Rims and shared by transforms
    hidden_paths = Om.MDagPathArray()
    last_hidden_node = ''
    search = '.*?({})'

    for dag_path in dag_path_iterator(traversal_type=Om.MItDag.kDepthFirst):
        full_path = dag_path.fullPathName()

        if not dag_path.isVisible():
            m = None
            # Check if we are inside a child path of an already added path
            # !IMPORTANT! works only with iterator set to depthFirst
            if last_hidden_node:
                m = re.search(search.format(last_hidden_node), full_path)

            # Do not add cameras, instances or childs of already hidden objects
            if not dag_path.hasFn(Om.MFn.kCamera) and not dag_path.isInstanced() and not m:
                hidden_paths.append(dag_path)
                # Unique path to this hidden node(in allmighty unicode encoded as utf-8)
                last_hidden_node = unicode(dag_path.partialPathName()).encode('utf-8')

    if hidden_paths:
        delete(hidden_paths)


def empty_groups():
    """
        Brute force delete all empty groups, waiting for inspiration
        to only delete highest empty hierarchy path
    """
    while True:
        empty_paths = Om.MDagPathArray()

        for m_path in dag_path_iterator():
            if not m_path.childCount():
                empty_paths.append(m_path)

        if not empty_paths:
            break

        delete(empty_paths)


def all_lights():
    """ Removes all Om.MFn.kLight objects and their transform parents """
    light_transform_paths = Om.MDagPathArray()

    for dag_path in dag_path_iterator(filter_type=Om.MFn.kLight):
        # Get parent transform node and delete it
        transform_obj = dag_path.transform()

        if not transform_obj.isNull():
            light_transform_paths.append(Om.MFnDagNode(transform_obj).getPath())

    delete(light_transform_paths)
