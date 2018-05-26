#! python 2 and 3
"""
    Methods to get basic paths

    Copyright (C) 2017 Stefan Tapper, All rights reserved.

        This file is part of Pfad Aeffchen.

        Pfad Aeffchen is free software: you can redistribute it and/or modify
        it under the terms of the GNU General Public License as published by
        the Free Software Foundation, either version 3 of the License, or
        (at your option) any later version.

        Pfad Aeffchen is distributed in the hope that it will be useful,
        but WITHOUT ANY WARRANTY; without even the implied warranty of
        MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
        GNU General Public License for more details.

        You should have received a copy of the GNU General Public License
        along with Pfad Aeffchen.  If not, see <http://www.gnu.org/licenses/>.
"""
import os
import copy
from modules.app_globals import *
from time import time

try:
    # Running from Python 3.x
    import winreg
except ImportError:
    # Running from Python 2.x
    import _winreg as winreg


def get_user_directory():
    """ Return a user writeable directory """
    usr_profile = os.environ.get('USERPROFILE', None) or os.path.expanduser('~')
    document_path = os.path.join(usr_profile, 'Documents/maya')

    # Choose usr/Documents/maya if present
    if os.path.exists(document_path):
        usr_profile = document_path

    return usr_profile


def get_current_modules_dir():
    """ Return path to this app modules directory """
    # Path to this module
    current_path = os.path.dirname(__file__)

    # Traverse one directoy up
    current_path = os.path.abspath(os.path.join(current_path, '../'))

    return current_path


def create_unique_render_path(scene_file, dir_path):
    """ Creates unique render path """
    if scene_file:
        name_prefix = os.path.basename(scene_file)[0:8]
    else:
        name_prefix = 'Unbenannt'

    render_sub_dir = '{0}_{1:.4f}'.format(name_prefix, time()).replace('.', '_')
    render_sub_dir = os.path.join(OUTPUT_DIR_NAME, render_sub_dir)
    dir_path = os.path.join(dir_path, render_sub_dir)

    if not os.path.exists(dir_path):
        os.makedirs(dir_path)

    return dir_path


def get_maya_version(version=DEFAULT_VERSION, __return_path=False):
    key = None
    try_versions = copy.copy(COMPATIBLE_VERSIONS)

    if version:
        try_versions.append(version)

    while try_versions:
        version = try_versions.pop()

        key_str = 'SOFTWARE\\Autodesk\\Maya\\' + version + '\\Setup\\InstallPath'
        reg = winreg.ConnectRegistry(None, winreg.HKEY_LOCAL_MACHINE)

        try:
            key = winreg.OpenKey(reg, key_str, 0, winreg.KEY_READ)
        except WindowsError as e:
            __msg = 'No Windows registry entry for Maya ' + version
            print(__msg)
            del e, __msg

        if key:
            break

    if not key:
        return None

    if __return_path:
        # Return Maya install location
        try:
            maya_app_dir, regtype = winreg.QueryValueEx(key, 'MAYA_INSTALL_LOCATION')
        except Exception as e:
            print(e)
            return None

        return maya_app_dir
    else:
        # Return Maya version
        return version


def get_maya_install_location(version=DEFAULT_VERSION):
    """ Return the Maya installation location or None if not found from the Windows Registry """

    return get_maya_version(version, True)


def get_mayapy_path(version=None):
    if version is None:
        version = DEFAULT_VERSION

    # Get Maya installation path
    maya_dir = os.environ.get('MAYA_LOCATION', get_maya_install_location(version))

    maya_py = os.path.join(maya_dir, 'bin/mayapy.exe')
    return os.path.abspath(maya_py)
