#! usr/bin/python_2
"""
    Image file utilitys run from within Maya standalone


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
import re
import glob
from time import time, sleep
import threading
import maya.cmds as cmds
from maya_mod.start_mayapy import run_module_in_standalone
from maya_mod.maya_canvas import Canvas
from modules.app_globals import ImgParams
from modules.setup_log import setup_logging
from maya_mod.socket_client import send_message

LOGGER = setup_logging(__name__)


class CheckImageThread(threading.Thread):
    """ Run a worker thread to detect empty images """
    def __init__(self, img_file, env):
        super(CheckImageThread, self).__init__()

        # Path to image files
        self.img_file = img_file

        # Environment paths
        self.env = env

    def run(self):
        img_check_module = os.path.abspath(os.path.join(self.env, 'maya_mod/run_empty_img_check.py'))

        # Run Maya standalone to detect and delete empty image files
        process = run_module_in_standalone(img_check_module, self.img_file, self.env)
        process.wait()


class MayaImgUtils(object):
    @staticmethod
    def iter_image_files(img_path, img_ext):
        """ Glob iterate img_path and return files *.img_ext """
        for __img_file in glob.glob(img_path + '/*.' + img_ext):
            yield __img_file

    @classmethod
    def delete_empty_images_threaded(cls, img_path, img_ext=ImgParams.extension, env=''):
        """ Obsolete with Image Watcher process """
        """
            Check for empty images in own Maya Standalone threads
        """

        def join_threads(thread_list):
            if not len(thread_list):
                return

            LOGGER.info('Joining %s threads', len(thread_list))

            while thread_list:
                __thread = thread_list.pop()
                __timeout = time()

                while __thread.isAlive():
                    LOGGER.info('Joining %s', __thread.getName())
                    __thread.join(timeout=120.0)

                    if time() - __timeout > 600.0:
                        LOGGER.error('Thread %s timed out.', __thread.getName())
                        break

        def cpu_count(num_cpu=6):
            if 'NUMBER_OF_PROCESSORS' in os.environ.keys():
                __os_cpu = int(os.environ['NUMBER_OF_PROCESSORS'])
                num_cpu = max(1, int(round(__os_cpu * 0.5)))

            return num_cpu

        # Start time
        __s = time()
        # Image list
        __img_list = list()
        # Check image thread helper class
        __cs = CheckImageThread
        # Number of threads allowed
        __num_cpu = cpu_count()

        # Create list of image files
        for __i in cls.iter_image_files(img_path, img_ext):
            __img_list.append(__i)

        send_message('Bilderkennung benutzt {0} Threads fuer {1} Bilder'.format(__num_cpu, len(__img_list)))
        LOGGER.info('======================================')
        LOGGER.info('Starting empty image detection')
        LOGGER.info('using %s threads for %s images', __num_cpu, len(__img_list))
        LOGGER.info('======================================')

        # Prepare thread list
        __t = list()

        # Create thread per image
        while __img_list:
            __img = __img_list.pop()

            # Create thread
            __img_thread = __cs(__img, env)
            __img_thread.setDaemon(False)
            __img_thread.start()

            __t.append(__img_thread)

            __img_name = os.path.split(__img)[-1]
            LOGGER.info('Started image detection thread #%s/%s for image %s',
                        max(0, len(__t)), __num_cpu, __img_name)
            send_message('Starte Thread {0}/{1} fuer Datei:<i> {2}</i>'.format(
                max(0, len(__t)), __num_cpu, __img_name))

            # Have a break while a new maya standalone initializes
            sleep(3)

            if len(__t) >= __num_cpu:
                join_threads(__t)

        join_threads(__t)

        # Report duration
        __duration = time() - __s
        __m, __s = divmod(__duration, 60)
        LOGGER.info('Image detection duration: {:02.0f}:{:02.0f}'.format(__m, __s))
        send_message('Bilderkennung abgeschlossen in {:02.0f}min:{:02.0f}sec'.format(__m, __s))

    @staticmethod
    def open_as_maya_image(img_file):
        return Canvas.from_file(img_file)

    @classmethod
    def detect_empty_image(cls, img_file):
        """
            Use MImage to detect if the provided image is empty.
            We assume an RGBA image.
        """
        __img = cls.open_as_maya_image(img_file)
        return cls.detect_empty_m_image(__img)

    @staticmethod
    def detect_empty_m_image(maya_img_object):
        """
            Use MImage to detect if the provided image is empty.
            We assume an RGBA image.
        """
        w, h = int(maya_img_object.width), int(maya_img_object.height)

        if w is None or h is None:
            return False

        for x in range(0, w):
            for y in range(0, h):
                _, _, _, __alpha = maya_img_object[x, y]

                if __alpha > 0:
                    del maya_img_object
                    # Image is not empty
                    return False

        del maya_img_object
        # Image is empty
        return True

    @classmethod
    def delete_empty_images(cls, img_path, img_ext):
        __s = time()

        for __img in cls.iter_image_files(img_path, img_ext):
            LOGGER.debug('Searching for empty image in %s', __img)
            __r = cls.detect_empty_image(__img)

            __img_name = os.path.split(__img)[-1]
            if __r:
                LOGGER.debug('Deleting empty image: %s', __img_name)
                cls.delete_image_file(__img)

        __duration = time() - __s
        LOGGER.info('Duration: {:.3f}'.format(__duration))

    @staticmethod
    def delete_image_file(img_file):
        try:
            LOGGER.info('Removing image: %s', img_file)
            os.remove(img_file)
        except Exception as e:
            LOGGER.error('Could not delete image file: %s\n%s', img_file, e)
            return False

        return True

    @classmethod
    def create_layered_psd(cls, psd_file, img_path, img_ext=ImgParams.extension,
                           res_x=ImgParams.res_x, res_y=ImgParams.res_y, rem_single_imgs=False):
        """
        Create a layered psd file from image files in img_path with extension img_ext
        Returns True on success
        """
        if not os.path.exists(img_path):
            return False

        __psd_layer = list()
        for __img_file in cls.iter_image_files(img_path, img_ext):
            # Remove unwanted prefixes
            __layer_name = mladenka_renamer(os.path.split(__img_file)[-1][:-4])

            # Add psd layer tuple
            __psd_layer.append((__layer_name, 'Normal', __img_file))

        if __psd_layer:
            __psd_layer = sorted(__psd_layer, reverse=True)

            try:
                cmds.createLayeredPsdFile(psf=psd_file, xr=res_x, yr=res_y, ifn=__psd_layer)
            except Exception as e:
                LOGGER.error(e)

            if os.path.exists(psd_file) and rem_single_imgs:
                for __img in cls.iter_image_files(img_path, img_ext):
                    try:
                        os.remove(__img)
                    except Exception as e:
                        LOGGER.error(e)

            return True

        return False


def mladenka_renamer(name):
    # Replace target looks t_
    # eg. t_name -> name
    try:
        name = re.sub(r"^t_", '', name)
    except Exception as e:
        LOGGER.error(e)

    # Remove layer number and _pfad
    # eg. int_name_123_pfad -> int_name
    try:
        pattern = r'(_+)(\d\d\d)(_+)(.*)'
        name = re.sub(pattern, r'', name)
    except Exception as e:
        LOGGER.error(e)

    # Move int_ etc to end
    # eg. int_name -> name_int
    try:
        pattern = r'(^int|ext|miko|tuer|itafel+)(_+)(.*)'
        name = re.sub(pattern, r'\3\2\1', name)
    except Exception as e:
        LOGGER.error(e)

    return name
