#! usr/bin/python_3
"""
Render -r <renderer name> <options> <filename>
sw = software renderer
hw = hardware renderer
vr = vector renderer
hw2 = hardware 2.0 renderer
file = the file within which the renderer is specified

-rd <path>          output path
-im <filename>      img file name
-of <format>        output format

Uses scene specific renderer if <renderer name> is not specified

maya bin directory: Render.exe

Test Paths:
C:\\Users\\CADuser\\Nextcloud\\py\\maya_scripts\\render_output
f = 'c:\\Users\\CADuser\\Nextcloud\\py\\py_knecht\\_work\\A7NF_freigestellte_Sitze\\A7NF_freigestellte_Sitze_render.mb'
o = 'C:\\Users\\CADuser\\Nextcloud\\py\\maya_scripts\\render_output'
import modules.maya_command_line_render as mr

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
import subprocess as sp
from modules.setup_paths import get_mayapy_path

ABOVE_NORMAL_PRIORITY_CLASS = 0x00008000
BELOW_NORMAL_PRIORITY_CLASS = 0x00004000
HIGH_PRIORITY_CLASS = 0x00000080
IDLE_PRIORITY_CLASS = 0x00000040
NORMAL_PRIORITY_CLASS = 0x00000020
REALTIME_PRIORITY_CLASS = 0x00000100


def run_command_line_render(my_file, out_dir, res_x, res_y, version, logger, image_format: str='iff'):
    global LOGGER
    LOGGER = logger

    maya_bin_dir = os.path.abspath(os.path.dirname(get_mayapy_path(version)))
    renderer_path = os.path.abspath(os.path.join(maya_bin_dir, 'Render.exe'))

    img_name = '-im "<RenderLayer>" '
    out_dir = '-rd "' + out_dir + '" '
    res_x = '-x ' + str(res_x) + ' '
    res_y = '-y ' + str(res_y) + ' '
    my_file = '"' + os.path.abspath(my_file) + '"'
    image_format = '-of ' + image_format + ' '

    # Prepare arguments list
    __arg_string = renderer_path + ' ' + img_name + out_dir + res_x + res_y + image_format + my_file

    LOGGER.debug('Running command line render with arguments:\n%s', __arg_string)

    # Run Maya command line render
    my_env = dict()
    my_env.update(os.environ)
    if 'MAYA_PLUG_IN_PATH' in my_env.keys():
        LOGGER.info('Creating environment without MAYA_PLUG_IN_PATH to fix mayaHardware2 not rendering issue.')
        my_env.pop('MAYA_PLUG_IN_PATH')
    process = sp.Popen(__arg_string, env=my_env, stdout=sp.PIPE, stderr=sp.STDOUT,
                       creationflags=IDLE_PRIORITY_CLASS)

    return process
