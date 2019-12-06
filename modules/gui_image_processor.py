#! usr/bin/python_3
"""
    Module to watch a folder for created and removed files

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
import shutil
import numpy as np
from PIL import Image
from time import sleep
from pathlib import Path
from PyQt5 import QtCore
from subprocess import TimeoutExpired

from modules.create_cryptomatte import CreateCryptomattes
from modules.detect_lang import get_translation
from modules.setup_log import setup_queued_logger
from modules.check_file_access import CheckFileAccess
from modules.app_globals import *
from maya_mod.start_mayapy import run_module_in_standalone

# translate strings

de = get_translation()
_ = de.gettext


def file_is_locked(file_path):
    """ Dirty method to check if a file is opened by another process on MS Windows """
    file_object = None

    try:
        file_object = open(file_path, 'a', buffering=8)
        file_lock = False
    except OSError:
        file_lock = True
    finally:
        if file_object:
            file_object.close()

    return file_lock


def check_file_in_use(img_file: Path):
    """ Check if file is accessed by another process """
    try:
        file_access = CheckFileAccess(img_file)

        if file_access.check():
            LOGGER.debug('File in use by another process: %s - %s', file_access.process_id, file_access.process_name)
            return True
    except Exception as e:
        LOGGER.error('Error checking file usage. %s', e)

    return False


class FileDirectoryWorker:
    # Look for files with the following extension
    image_file_extension = ImgParams.extension

    @classmethod
    def index_img_files(cls, img_file_dir: Path):
        img_file_dict = dict()

        try:
            if not img_file_dir.exists():
                LOGGER.error('Can not find image output directory. Nothing to index.')
                return img_file_dict
        except OSError as e:
            LOGGER.error('Can not find image output directory. Nothing to index.')
            LOGGER.error(e)
            return img_file_dict

        for __img_file in img_file_dir.glob('*' + cls.image_file_extension):
            # --------------------------------------------
            # Check file size
            try:
                file_size = __img_file.stat().st_size
                if file_size < 350000:
                    # Skip small files that are have just been written by the renderer
                    # 4K empty iff image file should be at least 539 kB
                    continue
            except FileNotFoundError or OSError as e:
                LOGGER.error('Error indexing image: %s', e)
                # File probably deleted while watching, skip
                continue

            # Image key
            img_key = __img_file.stem

            # Create image file dict entry
            img_file_dict.update({img_key: dict(path=__img_file)})

        return img_file_dict

    @staticmethod
    def difference(old_dict, new_dict):
        current_files = set(old_dict)
        new_files = set(new_dict)

        return new_files.difference(current_files)


class ImageFileWatcher(QtCore.QThread):
    file_created_signal = QtCore.pyqtSignal(set, int)
    file_removed_signal = QtCore.pyqtSignal(set)
    status_signal = QtCore.pyqtSignal(str)
    psd_created_signal = QtCore.pyqtSignal()
    img_job_failed_signal = QtCore.pyqtSignal()

    led_signal = QtCore.pyqtSignal(int, int)

    # Scan interval in milliseconds
    interval = 15000

    # Thread Pool
    # increase thread timeout to 4 mins
    thread_timeout = 240000
    max_threads = 10

    # Scene file name
    scene_file_name = _('KeineSzenenDatei')

    def __init__(self, parent, output_dir, scene_file, mod_dir, logging_queue):
        super(ImageFileWatcher, self).__init__()

        # Add queue handler to logger
        global LOGGER
        LOGGER = setup_queued_logger(__name__, logging_queue)

        self.watch_active = False
        self.output_dir = Path(output_dir)

        self.watcher_img_dict = dict()
        self.processed_img_dict = dict()

        # File directory index worker
        self.directory = FileDirectoryWorker()

        # Timers
        self.unprocessed_imgs_timer = QtCore.QTimer()
        self.watch_timer = QtCore.QTimer()

        # Setup event loop specific timers inside thread event loop
        self.started.connect(self.initialize_event_loop)

        if scene_file:
            self.scene_file_name = Path(scene_file).stem
        self.scene_file = scene_file

        self.mod_dir = mod_dir
        self.parent = parent

        # Called when rendering is finished
        self.create_psd_requested = False
        self.force_psd_creation = False
        self.is_arnold = False

        # Prepare thread pool
        self.thread_pool = QtCore.QThreadPool(parent=self)
        thread_count = max(1, min(self.max_threads, round(self.idealThreadCount() * 0.3)))
        self.thread_pool.setMaxThreadCount(thread_count)
        self.thread_pool.setExpiryTimeout(self.thread_timeout)

        self.status_signal.connect(self.parent.signal_receiver)
        self.file_created_signal.connect(self.parent.file_created)
        self.file_removed_signal.connect(self.parent.file_removed)
        self.psd_created_signal.connect(self.parent.psd_created)
        self.img_job_failed_signal.connect(self.parent.img_job_failed)
        self.led_signal.connect(self.parent.led)

        # Init message
        self.status_signal.emit(_('Bilderkennung verfügt über {0:02d} parallel ausführbare '
                                  'Threads auf dieser Maschine. '
                                  '{1:02d} Threads aktiv.')
                                .format(thread_count, self.thread_pool.activeThreadCount()))

        # Properties
        self.__img_count = 0
        self.__previous_imgs = set()

    @property
    def img_count(self):
        return self.__img_count

    @img_count.setter
    def img_count(self, val):
        self.__img_count += val

    @img_count.deleter
    def img_count(self):
        self.__img_count = 0

    @property
    def previous_imgs(self):
        return self.__previous_imgs

    @previous_imgs.setter
    def previous_imgs(self, val: set):
        self.__previous_imgs = val

    @previous_imgs.deleter
    def previous_imgs(self):
        self.__previous_imgs = set()

    def run(self):
        self.exec()
        LOGGER.error('Image File Watcher thread ended.')

    def initialize_event_loop(self):
        LOGGER.debug('Initializing Image File Watcher event loop.')

        # Timer for file watcher loop
        self.watch_timer = QtCore.QTimer()
        self.watch_timer.setSingleShot(False)
        self.watch_timer.setInterval(self.interval)
        self.watch_timer.timeout.connect(self.watch)
        self.watch_timer.start()
        LOGGER.debug('Watch Timer: %s', self.watch_timer.remainingTime())

        # Unprocessed images timeout
        self.unprocessed_imgs_timer = QtCore.QTimer()
        self.unprocessed_imgs_timer.setSingleShot(True)
        self.unprocessed_imgs_timer.setInterval(240000)
        self.unprocessed_imgs_timer.timeout.connect(self.unprocessed_imgs_timed_out)
        LOGGER.debug('Unprocessed Timout Timer: %s', self.unprocessed_imgs_timer.remainingTime())

        LOGGER.info('Image File Watcher thread event loop started.')

    def reset(self):
        self.unprocessed_imgs_timer.stop()

        self.create_psd_requested = False
        self.is_arnold = False

        # Clear queue of QRunnables thar are not started yet
        self.thread_pool.clear()

        # Resets directory file index
        self.watcher_img_dict = dict()

        # Reset image count
        del self.img_count

        # Reset previous image
        del self.previous_imgs

    def deactivate_watch(self):
        self.watch_active = False
        self.status_signal.emit(_('Ordnerüberwachung eingestellt.'))

    def watch(self):
        # Red LED on while image detection threads active
        if self.thread_pool.activeThreadCount() > 0:
            self.led_signal.emit(0, 1)

        # Make sure we only call this loop if thread is not busy with eg. detecting images
        self.watch_timer.stop()

        # Process output folder
        if self.watch_active:
            self.led_signal.emit(2, 1)
            self.watch_folder()
            self.led_signal.emit(2, 2)

        # Check if rendering was finished and all images processed
        if self.create_psd_requested:
            self.led_signal.emit(2, 1)
            self.create_psd()
            self.led_signal.emit(2, 2)

        self.led_signal.emit(1, 0)

        # Watcher is ready again, re-schedule a run in next interval
        self.watch_timer.start()

    def watch_folder(self):
        if self.is_arnold:
            return

        img_dict = self.directory.index_img_files(self.output_dir)
        self.report_changes(img_dict)

        # Watch for arnold render results
        if (self.output_dir / ImgParams.cryptomatte_dir_name).exists() or (self.output_dir / 'beauty').exists():
            self.is_arnold = True

        self.watcher_img_dict = img_dict

    def initial_directory_index(self):
        # Resets property
        self.reset()

        # Index existing files on initial watch
        self.watcher_img_dict = self.directory.index_img_files(self.output_dir)

        LOGGER.info('Image File Watcher directory changed. Found %s already existing files.',
                    len(self.watcher_img_dict))
        self.status_signal.emit(_('Initiale Ordnerindexierung abgeschlossen: '
                                '{0:02d} bereits existierende Dateien gefunden.')
                                .format(len(self.watcher_img_dict)))

        # Initial index finished, continue file watch
        self.led_signal.emit(1, 0)
        self.led_signal.emit(2, 0)
        self.watch_active = True

    def unprocessed_imgs_timed_out(self):
        """ Enforce Psd creation, verification of unprocessed images timed out """
        self.create_psd_request(force_psd_creation=True)
        self.status_signal.emit(_('Fehler: Überprüfung bereits bearbeiteter Bilder fehlgeschlagen. PSD Erstellung wird '
                                  'nun erzwungen.'))

    def create_psd_request(self, force_psd_creation=False):
        """ Called from mother ship """
        self.create_psd_requested = True
        self.force_psd_creation = force_psd_creation

        if force_psd_creation:
            self.status_signal.emit(_('PSD Erstellung wird erzwungen sobald Bilderkennungsthreads '
                                      'abgeschlossen sind.'))

    def create_psd(self):
        """ Check that all images in the directory are processed and create layered PSD file """
        if self.thread_pool.activeThreadCount():
            # Threads detecting empty images are running, abort
            LOGGER.debug('Can not create PSD yet. Image detection threads active. Retrying on next directory index.')
            return

        # Default resolution values
        # will be overriden if cryptomatte and use_scene_settings active
        img_resolution = (ImgParams.res_x, ImgParams.res_y)

        if self.is_arnold:
            self.status_signal.emit(_('Cryptomatten werden erstellt.'))
            # self.file_created_signal.emit(set(), 3)

            c = CreateCryptomattes(self.output_dir, self.scene_file, LOGGER)
            self.watcher_img_dict, self.processed_img_dict = c.create_cryptomattes()
            img_resolution = (c.res_x, c.res_y)

        if not len(self.watcher_img_dict):
            # No images to create PSD from, set Job as failed
            LOGGER.error('PSD requested but no images to process. Resetting image watcher.')
            self.img_job_failed_signal.emit()
            self.reset()
            self.deactivate_watch()
            return

        # Check for unprocessed files
        not_processed = list()
        create_psd = True

        for __i in self.watcher_img_dict.items():
            img_key, img_file_dict = __i

            if img_key not in self.processed_img_dict.keys():
                create_psd = False
                not_processed.append(f'{img_key} - {img_file_dict.get("path")}')

        if not create_psd:
            # Force PSD creation after timeout
            if not self.unprocessed_imgs_timer.isActive():
                self.unprocessed_imgs_timer.start()
                LOGGER.debug('Starting unprocessed images timeout timer. Rem: %s',
                             self.unprocessed_imgs_timer.remainingTime())

            LOGGER.debug('Can not create PSD yet. Some indexed images are not yet processed. '
                         'Retrying on next directory index.')
            LOGGER.error('Possibly unprocessed image files:\n%s\n'
                         'unprocessed timeout remaining: %s',
                         not_processed, self.unprocessed_imgs_timer.remainingTime())

        # Create psd if every image file is processed OR if force PSD creation requested
        if create_psd or self.force_psd_creation:
            self.unprocessed_imgs_timer.stop()
            self.status_signal.emit(_('PSD wird erstellt.'))

            psd_file_name = self.scene_file_name + _('_Pfade.psd')
            psd_file = self.output_dir / psd_file_name

            LOGGER.debug('Starting PSD Thread: %s %s %s', psd_file, self.output_dir, self.mod_dir)

            if self.is_arnold:
                file_ext = ImgParams.cryptomatte_out_file_ext
            else:
                file_ext = ImgParams.extension

            create_psd_runner = CreatePSDFile(
                psd_file, self.output_dir, self.mod_dir, self.thread_status, self.psd_created,
                file_ext_override=file_ext, img_resolution=img_resolution
                )

            self.thread_pool.start(create_psd_runner)

            self.create_psd_requested = False
            self.force_psd_creation = False

    def psd_created(self, psd_file):
        self.unprocessed_imgs_timer.stop()

        LOGGER.info('PSD File creation finished.')

        # Remove arnold render results
        if self.is_arnold:
            try:
                shutil.rmtree(Path(self.output_dir / 'beauty').as_posix(), ignore_errors=True)
                shutil.rmtree(Path(self.output_dir / ImgParams.cryptomatte_dir_name).as_posix(), ignore_errors=True)
            except Exception as e:
                LOGGER.error('Error removing arnold render results: %s', e)

        self.status_signal.emit(_('PSD Erstellung abgeschlossen für {}.').format(psd_file))
        self.psd_created_signal.emit()
        self.led_signal.emit(0, 2)

        self.deactivate_watch()

    def change_output_dir(self, directory):
        """
            Change watched directory and reset existing image entries
            Called from parent process.
        """
        # Disable file watch until initial directory index
        self.watch_active = False

        self.output_dir = Path(directory)

        if not self.output_dir.exists():
            self.output_dir.mkdir()

        self.status_signal.emit(_('Überwache Ordner: <b>{}</b>').format(self.output_dir.as_posix()))

        self.initial_directory_index()

    def change_scene_file(self, file):
        self.scene_file_name = Path(file).stem
        self.scene_file = file
        self.status_signal.emit(_('Szenendatei geändert zu: {}').format(self.scene_file_name))

    def report_changes(self, current_img_dict):
        self.check_for_created_files(current_img_dict)
        self.check_for_removed_files(current_img_dict)

    def check_for_created_files(self, img_dict):
        new_file_set = self.directory.difference(old_dict=self.watcher_img_dict, new_dict=img_dict)

        if not new_file_set:
            if not self.create_psd_requested:
                # No new files, rendering not finished
                return

            if self.previous_imgs:
                # Rendering finished, process previous files
                new_file_set = self.previous_imgs
                del self.previous_imgs
            else:
                # Rendering finished but no previous unprocessed files
                return
        else:
            # Add new files to created image count
            self.img_count = len(new_file_set)

            LOGGER.debug('Watcher found new files: %s', new_file_set)

            # Inform the parent thread
            self.file_created_signal.emit(new_file_set, self.img_count)

        if self.create_psd_requested:
            # PSD requested, save to access all files because the rendering thread is finished.
            # Start image detection process for last added file-s
            self.add_new_file_set_as_threads(img_dict, new_file_set)
        else:
            # Not save to access last created file-s as rendering thread is active.
            # Process the previous created image-s
            self.add_new_file_set_as_threads(img_dict, self.previous_imgs)
            self.previous_imgs = new_file_set

    def add_new_file_set_as_threads(self, img_dict, new_file_set):
        """ check_for_created_files helper """
        for img_key in new_file_set:
            img_entry = img_dict.get(img_key)

            if img_entry:
                img_file = img_entry.get('path')
            else:
                # This happens when new_file_set=self.previous_imgs and the image detection process
                # already deleted the file and therefore it is not indexed in the freshly acquired img_dict
                # So skip this entry as it is already processed
                continue

            if img_file:
                self.add_image_processing_thread(img_file)

    def add_image_processing_thread(self, img_file):
        # -----
        # Use pillow detection if format is not Maya IFF files
        if img_file.suffix[-3:] != ImgParams.maya_detection_format:
            self.status_signal.emit(_('<i>{0}</i> wird in Pillow Bilderkennung untersucht.').format(img_file.name))
            self.detect_empty_image_pil(img_file)
            return

        # -----
        # Maya image detection process
        # Create runnable and append to thread pool
        img_thread = ProcessImage(img_file, self.mod_dir, self.image_processing_result, self.thread_status)
        self.thread_pool.start(img_thread)

        self.status_signal.emit(_('<i>{0}</i> zur Bilderkennung eingereiht. '
                                  '{1:02d}/{2:02d} Threads aktiv.')
                                .format(img_file.name,
                                        self.thread_pool.activeThreadCount(),
                                        self.thread_pool.maxThreadCount())
                                )

    def detect_empty_image_pil(self, img_file: Path):
        self.led_signal.emit(0, 1)
        image_is_empty = True

        # --- Detect image contents ---
        try:
            with Image.open(img_file.as_posix()) as img:
                img_array = np.asarray(img)

                if img_array.max() > 0:
                    image_is_empty = False

            del img
        except Exception as e:
            LOGGER.error('Error reading file for image detection: %s', e)

        # --- Result ---
        # Image is -not- empty
        if not image_is_empty:
            LOGGER.debug('Image containing pixel data detected: %s', img_file.stem)
            self.status_signal.emit(_('Bilderkennung abgeschlossen für {}. Bildinhalte erkannt.')
                                    .format(img_file.name)
                                     )
            self.image_processing_result(img_file)
            return

        # Image is empty
        LOGGER.debug('Empty image detected, will try to delete: %s', img_file.stem)
        self.status_signal.emit(_('Bilderkennung abgeschlossen für {}. '
                                  '<i>Keine Bildinhalte erkannt.</i>')
                                .format(img_file.name)
                                 )

        # Remove the empty file
        try:
            os.remove(img_file)
            self.led_signal.emit(0, 2)
        except Exception as e:
            LOGGER.error('Could not delete empty image file. %s', e)
            # Set un-removable files as processed
            self.image_processing_result(img_file)

    def check_for_removed_files(self, img_dict):
        rem_file_set = self.directory.difference(old_dict=img_dict, new_dict=self.watcher_img_dict)

        if not rem_file_set:
            return

        LOGGER.debug('Watcher found removed files: %s', rem_file_set)

        # Reset watcher img dict
        self.watcher_img_dict = dict()
        self.watcher_img_dict = img_dict

        self.file_removed_signal.emit(rem_file_set)

    def image_processing_result(self, img_file: Path):
        """ Called from image processing thread """
        self.processed_img_dict[img_file.stem] = dict(path=img_file, processed=True)

        # Switch Red LED off
        self.led_signal.emit(0, 2)

    def thread_status(self, msg):
        """ Status signals emitted from image processing or psd threads """
        self.status_signal.emit(msg)


class ProcessImageSignals(QtCore.QObject):
    result = QtCore.pyqtSignal(Path)
    status = QtCore.pyqtSignal(str)


class ProcessImage(QtCore.QRunnable):
    image_process_timeout = 360  # 6 minutes

    def __init__(self, img_file, mod_dir, result_callback, status_callback):
        super(ProcessImage, self).__init__()
        self.process = None
        self.mod_dir = mod_dir
        self.img_file = img_file
        self.img_check_module = Path(self.mod_dir) / 'maya_mod/run_empty_img_check.py'

        # Prepare signals
        self.signals = ProcessImageSignals()
        self.signals.result.connect(result_callback)
        self.signals.status.connect(status_callback)

    def run(self):
        # Hopefully avoid race conditions while accessing files
        sleep(3)

        self.run_process()
        self.detect_result()

    def run_process(self):
        """ Run Maya standalone to detect and delete empty image file """
        try:
            LOGGER.debug('Running image detection process for %s', self.img_file.as_posix())

            self.process = run_module_in_standalone(
                self.img_check_module.as_posix(),
                self.img_file.as_posix(),
                self.mod_dir,
                pipe_output=True
                )
        except Exception as e:
            LOGGER.error(e)
            self.signals.status.emit(_('Fehler im Bilderkennungsprozess:\n{}').format(e))

            # Process could not be started, abort
            return None, None

        # Wait for the process to finish
        try:
            outs, errs = self.process.communicate(input=None, timeout=self.image_process_timeout)
        except TimeoutExpired:
            LOGGER.error('Image detection process timed out. Killing process.')
            self.kill_process()
            outs, errs = self.process.communicate(input=None)
            LOGGER.error('Output: %s\nErrors: %s', outs, errs)

        return outs, errs

    def detect_result(self):
        """ Detect if the image was deleted and report result to parent """
        if self.img_file.exists():
            self.signals.status.emit(_('Bilderkennung abgeschlossen für {}. Bildinhalte erkannt.')
                                     .format(self.img_file.name)
                                     )
            self.signals.result.emit(self.img_file)
        else:
            self.signals.status.emit(_('Bilderkennung abgeschlossen für {}. '
                                       '<i>Keine Bildinhalte erkannt.</i>')
                                     .format(self.img_file.name)
                                     )

    def kill_process(self):
        if self.process:
            try:
                self.process.kill()
                LOGGER.info('Image content detection process killed.')
            except Exception as e:
                LOGGER.error('Killing the Image content detection process failed!')
                LOGGER.error(e)


class CreatePSDFileSignals(QtCore.QObject):
    result = QtCore.pyqtSignal(str)
    status = QtCore.pyqtSignal(str)


class CreatePSDFile(QtCore.QRunnable):

    def __init__(self, psd_file, img_dir, mod_dir, status_callback, result_callback,
                 file_ext_override='', img_resolution=(0, 0)):
        super(CreatePSDFile, self).__init__()
        self.psd_file, self.img_dir, self.mod_dir = psd_file, img_dir, mod_dir
        self.psd_creation_module = Path(self.mod_dir) / 'maya_mod/run_create_psd.py'

        self.file_extension = file_ext_override or ImgParams.extension
        self.img_res = (str(img_resolution[0]), str(img_resolution[1]))

        self.signals = CreatePSDFileSignals()
        self.signals.result.connect(result_callback)
        self.signals.status.connect(status_callback)

    def run(self):
        try:
            self.signals.status.emit(_('Erstelle PSD Datei {}').format(self.psd_file.name))
            process = run_module_in_standalone(
                self.psd_creation_module.as_posix(),  # Path to module to run
                self.psd_file.as_posix(), self.img_dir.as_posix(), self.file_extension, *self.img_res,  # Args
                Path(self.mod_dir).as_posix()  # Environment dir
                )
            process.wait()
        except Exception as e:
            LOGGER.error(e)

        # Mark PSD creation as finished even if unsuccessful to get the job finished
        self.signals.result.emit(self.psd_file.name)
