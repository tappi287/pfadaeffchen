#! usr/bin/python3 or !usr/bin/python2.7
"""
    Method to start a MayaPy Standalone process, this -must NOT be run- from mayapy interpreter

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
from modules.setup_log import setup_logging

LOGGER = setup_logging(__name__)


def run_module_in_standalone(module_file, *args, **kwargs):
    """
    Runs a mayapy Python interpreter and executes the provided module_file

    :param module_file: The python script file to execute in mayapy
    :type module_file: str
    :param args: Any additional string arguments that should be send to the python file
    :type args: str
    :keyword version: The Autodesk Maya version to use eg. '2017'
    :keyword pipe_output: bool - Returns a PIPE to STDOUT and STDERR
    :return: returns the Popen process object
    :rtype: subprocess.Popen
    """
    maya_py = None

    pipe_output, version = False, None
    if 'pipe_output' in kwargs.keys():
        pipe_output = kwargs['pipe_output']
    if 'version' in kwargs.keys():
        version = kwargs['version']

    # Get Maya installation path
    # if we already run in mayapy and version is None, will return 'MAYA_LOCATION' from os.environ
    maya_py = get_mayapy_path(version=version)

    if not maya_py:
        maya_py = get_mayapy_path(version='2017')

    if not maya_py:
        LOGGER.error('Could not find a Maya installation. Aborting.')
        return

    maya_dir = os.path.abspath(os.path.join(os.path.dirname(maya_py), '../'))

    # Prepare arguments list
    __arg_list = [maya_py, module_file]

    # Add arguments
    for __arg in args:
        if __arg:
            __arg_list = __arg_list + [__arg]

    __arg_string = ''
    for __arg in __arg_list:
        __arg_string += '"' + __arg + '" '
    __arg_string = __arg_string[0:-1]

    LOGGER.info('Starting Maya standalone with arguments\n%s\n', __arg_string)

    # Run Maya standalone
    if pipe_output:
        process = sp.Popen(__arg_list, stdout=sp.PIPE, stderr=sp.STDOUT)
    else:
        process = sp.Popen(__arg_list)

    return process


def runtime_environment(maya_py, maya_dir, *new_paths):
    """
        Returns a new environment dictionary for this intepreter, with only the supplied paths
        (and the required maya paths).  Dictionary is independent of machine level settings;
        non maya/python related values are preserved.
    """

    runtime_env = os.environ.copy()

    quoted = lambda x: '%s' % os.path.normpath(x)

    # set both of these to make sure maya auto-configures
    # it's own libs correctly
    runtime_env['MAYA_LOCATION'] = os.path.dirname(maya_py)
    runtime_env['PYTHONHOME'] = os.path.dirname(maya_py)

    # use PYTHONPATH in preference to PATH
    runtime_env['PYTHONPATH'] = ";".join(map(quoted, new_paths))
    runtime_env['PATH'] = ''

    return runtime_env
