#! usr/bin/python_2
"""
    Run inside Maya Standalone instance and create psd file

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
import sys
import argparse

# Define command line arguments
parser = argparse.ArgumentParser()
# Positional argument 1 img_path
parser.add_argument('psd_file', help='Absolute path to the PSD file that should be created.', type=str)
parser.add_argument('img_path', help='Absolute path to the directory containing image files.', type=str)
parser.add_argument('file_ext', help='File extension of image files to look up eg. png', type=str)
parser.add_argument('env', help='Space separated, quoted Paths to extend the mayapy pythonpaths.', type=str)

# Parse command line arguments
args = parser.parse_args()

if args.env:
    for env_path in args.env.split(' '):
        if env_path not in sys.path:
            __msg = 'Extending sys path: ' + env_path
            print(__msg)
            sys.path.append(env_path)

from maya_mod.maya_image_util import MayaImgUtils

# Create layered PSD file from images and delete single image files
MayaImgUtils.create_layered_psd(
    args.psd_file, args.img_path, img_ext=args.file_ext, rem_single_imgs=True)
