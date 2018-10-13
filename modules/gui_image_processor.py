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
import threading
from time import sleep, time
from pathlib import Path
from PyQt5 import QtCore

from modules.detect_lang import get_translation
from modules.setup_log import add_queue_handler, setup_logging, setup_queued_logger
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


class ImageFileWatcher(QtCore.QThread):
    file_created_signal = QtCore.pyqtSignal(set, int)
    file_removed_signal = QtCore.pyqtSignal(set)
    status_signal = QtCore.pyqtSignal(str)
    psd_created_signal = QtCore.pyqtSignal()
    img_job_failed_signal = QtCore.pyqtSignal()

    led_signal = QtCore.pyqtSignal(int, int)

    # Scan interval in seconds
    interval = 15

    # Thread Pool
    # increase thread timeout to 4 mins
    thread_timeout = 240000
    max_threads = 10

    # Scene file name
    scene_file_name = _('KeineSzenenDatei')

    def __init__(self, parent, output_dir, scene_file, mod_dir, logging_queue):
        super(ImageFileWatcher, self).__init__(parent=parent)

        # Add queue handler to logger
        global LOGGER
        LOGGER = setup_queued_logger(__name__, logging_queue)

        self.watch_active = False
        self.output_dir = Path(output_dir)

        self.watcher_img_dict = dict()

        if scene_file:
            self.scene_file_name = Path(scene_file).stem

        self.mod_dir = mod_dir
        self.parent = parent

        # Called when rendering is finished
        self.create_psd_requested = False
        self.force_psd_creation = False

        # Prepare thread pool
        self.thread_pool = QtCore.QThreadPool(parent=self)
        thread_count = max(1, min(self.max_threads, round(self.idealThreadCount() * 0.3)))
        self.thread_pool.setMaxThreadCount(thread_count)
        self.thread_pool.setExpiryTimeout(self.thread_timeout)

        # Prepare a thread lock
        self.lock = threading.Lock()

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

        # Propertys
        self.__watcher_img_dict = dict()
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

    def acquire_lock(self, name: str='-not specified-'):
        LOGGER.debug('0 - ImageFileWatcher method "%s" acquires thread lock.', name)
        self.lock.acquire()
        LOGGER.debug('1 - "%s" acquired thread lock.', name)

    def release_lock(self, name: str='-not specified-'):
        self.lock.release()
        LOGGER.debug('2 - ImageFileWatcher method "%s" released thread lock.', name)

    def reset(self):
        self.create_psd_requested = False

        # Clear queue of QRunnables thar are not started yet
        self.thread_pool.clear()

        self.acquire_lock('reset')
        # Resets directory file index
        self.watcher_img_dict = dict()
        self.release_lock('reset')

        # Reset image count
        del self.img_count

        # Reset previous image
        del self.previous_imgs

    def deactivate_watch(self):
        self.watch_active = False
        self.status_signal.emit(_('Ordnerüberwachung eingestellt.'))

    def run(self):
        LOGGER.info('Image File Watcher starting.')
        if self.watch_active:
            self.initial_directory_index()

        while not self.isInterruptionRequested():
            # Red LED on while image detection threads active
            if self.thread_pool.activeThreadCount() > 0:
                self.led_signal.emit(0, 1)

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

            self.sleep(self.interval)
            self.led_signal.emit(1, 0)

        LOGGER.error('Image File Watcher thread ending.')

    def watch_folder(self):
        img_dict = self.index_img_files(set_processed=False)
        self.report_changes(img_dict)

        # Lock watcher img dict access
        self.acquire_lock('watch_folder')
        self.watcher_img_dict = img_dict
        self.release_lock('watch_folder')

    def initial_directory_index(self):
        # Resets property
        self.reset()

        # Index existing files on initial watch
        self.watcher_img_dict = self.index_img_files(set_processed=True)

        LOGGER.info('Image File Watcher directory changed. Found %s already existing files.',
                    len(self.watcher_img_dict))
        self.status_signal.emit(_('Initiale Ordnerindexierung abgeschlossen: '
                                '{0:02d} bereits existierende Dateien gefunden.')
                                .format(len(self.watcher_img_dict)))

        # Initial index finished, continue file watch
        self.led_signal.emit(1, 0)
        self.led_signal.emit(2, 0)
        self.watch_active = True

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

        create_psd = False
        if not len(self.watcher_img_dict):
            # No images to create PSD from, set Job as failed
            LOGGER.error('PSD requested but no images to process. Resetting image watcher.')
            self.img_job_failed_signal.emit()
            self.reset()
            self.deactivate_watch()
            return

        for __i in self.watcher_img_dict.items():
            img_key, img_file_dict = __i

            if not img_file_dict.get('processed'):
                # Some image(s) are not processed yet, skip
                LOGGER.debug('Can not create PSD yet. Some indexed images are not yet processed.'
                             'Retrying on next directory index.')
                if self.force_psd_creation:
                    continue
                else:
                    break
        else:
            # Break never called - everything should be processed
            create_psd = True

        # Create psd if every image file is processed OR if force PSD creation requested
        if create_psd or self.force_psd_creation:
            self.status_signal.emit(_('PSD wird erstellt.'))

            psd_file_name = self.scene_file_name + _('_Pfade.psd')
            psd_file = self.output_dir / psd_file_name

            LOGGER.debug('Starting PSD Thread: %s %s %s', psd_file, self.output_dir, self.mod_dir)
            create_psd_runner = CreatePSDFile(
                psd_file, self.output_dir, self.mod_dir, self.thread_status, self.psd_created
                )

            self.thread_pool.start(create_psd_runner)

            self.create_psd_requested = False
            self.force_psd_creation = False

    def psd_created(self, psd_file):
        LOGGER.info('PSD File creation finished.')
        self.status_signal.emit(_('PSD Erstellung abgeschlossen für {}.').format(psd_file))
        self.psd_created_signal.emit()
        self.led_signal.emit(0, 2)

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
        self.status_signal.emit(_('Szenendatei geändert zu: {}').format(self.scene_file_name))

    def index_img_files(self, set_processed=False):
        img_dict = dict()

        try:
            if not self.output_dir.exists():
                LOGGER.error('Can not find image output directory. Nothing to index.')
                return img_dict
        except OSError as e:
            LOGGER.error('Can not find image output directory. Nothing to index.')
            LOGGER.error(e)
            return img_dict

        for __img_file in self.output_dir.glob('*' + ImgParams.extension):
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
            img_dict.update({img_key: dict(path=__img_file)})
            # Update processed status
            img_dict.get(img_key).update(self.set_image_processed(__img_file, set_processed))

        return img_dict

    def report_changes(self, current_img_dict):
        self.check_for_created_files(current_img_dict)
        self.check_for_removed_files(current_img_dict)

    def check_for_created_files(self, img_dict):
        new_file_set = self.get_file_difference(old_dict=self.watcher_img_dict, new_dict=img_dict)

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
            img_file = img_dict.get(img_key).get('path')

            if img_file:
                self.add_image_processing_thread(img_file)

    def add_image_processing_thread(self, img_file):
        # Create runnable and append to thread pool
        img_thread = ProcessImage(img_file, self.mod_dir, self.image_processing_result, self.thread_status, self.lock)
        self.thread_pool.start(img_thread)

        max_threads = self.thread_pool.maxThreadCount()
        current_threads = self.thread_pool.activeThreadCount()

        self.status_signal.emit(_('<i>{0}</i> zur Bilderkennung eingereiht. '
                                  '{1:02d}/{2:02d} Threads aktiv.').format(img_file.name, current_threads, max_threads)
                                )

    def check_for_removed_files(self, img_dict):
        rem_file_set = self.get_file_difference(old_dict=img_dict, new_dict=self.watcher_img_dict)

        if not rem_file_set:
            return

        LOGGER.debug('Watcher found removed files: %s', rem_file_set)

        # Lock watcher img dict access
        self.acquire_lock('check_for_removed_files')

        # Reset watcher img dict
        self.watcher_img_dict = dict()
        self.watcher_img_dict = img_dict

        self.release_lock('check_for_removed_files')

        self.file_removed_signal.emit(rem_file_set)

    def set_image_processed(self, img_file: Path, processed: bool):
        img_entry = self.watcher_img_dict.get(img_file.stem)

        # If file exists in existing image entries get processed status from existing entry.
        # If entry is already set as processed, leave this status intact.
        # (and ignore method argument {processed: bool})
        if img_entry:
            existing_status = img_entry.get('processed')

            if existing_status is not None:
                img_path = img_entry.get('path')

                if img_path:
                    # Paths of existing entry and current image match?
                    if img_file == img_path:
                        # If existing status was already processed, ignore method argument
                        processed = existing_status
                    else:
                        # Report change of processed status
                        LOGGER.debug('Image detected as unprocessed. Setting %s to processed: %s', img_file.stem,
                                     self.watcher_img_dict[img_file.stem].get('processed'))

        return {'processed': processed}

    def image_processing_result(self, img_file: Path):
        """ Called from image processing thread """
        # Lock watcher img dict access
        self.acquire_lock('image_processing_result')

        file_dict = self.watcher_img_dict.get(img_file.stem)

        if file_dict:
            file_dict.update({'processed': True})

        LOGGER.debug('Image detection finished. Setting %s to processed: %s', img_file.stem,
                     self.watcher_img_dict[img_file.stem].get('processed'))

        self.release_lock('image_processing_result')

        # Switch Red LED off
        self.led_signal.emit(0, 2)

    def thread_status(self, msg):
        self.status_signal.emit(msg)

    @staticmethod
    def get_file_difference(old_dict, new_dict):
        current_files = set(old_dict)
        new_files = set(new_dict)

        return new_files.difference(current_files)


class ProcessImageSignals(QtCore.QObject):
    result = QtCore.pyqtSignal(Path)
    status = QtCore.pyqtSignal(str)


class ProcessImage(QtCore.QRunnable):
    file_lock_timeout = 30.0

    # Image process detection timeout
    # in case a maya standalone thread get's stuck, we will continue after 10 minutes
    detection_timeout = QtCore.QTimer()
    detection_timeout.setTimerType(QtCore.Qt.VeryCoarseTimer)
    detection_timeout.setInterval(600000)

    def __init__(self, img_file, mod_dir, result_callback, status_callback, lock):
        super(ProcessImage, self).__init__()
        self.process = None
        self.lock = lock
        self.mod_dir = mod_dir
        self.img_file = img_file
        self.img_check_module = Path(self.mod_dir) / 'maya_mod/run_empty_img_check.py'

        # Prepare signals
        self.signals = ProcessImageSignals()
        self.signals.result.connect(result_callback)
        self.signals.status.connect(status_callback)

        # Prepare timeout
        self.detection_timeout.timeout.connect(self.kill_process)

    def run(self):
        # Hopefully avoid race conditions while accessing files
        sleep(3)

        img_name = self.img_file.name

        self.detection_timeout.start()

        # Run process in try-except to avoid re-running this QRunnable on process errors
        try:
            # Run Maya standalone to detect and delete empty image file
            LOGGER.debug('Running image detection process for %s', self.img_file.as_posix())
            self.process = run_module_in_standalone(
                self.img_check_module.as_posix(), self.img_file.as_posix(), self.mod_dir)
            self.process.wait()
        except Exception as e:
            LOGGER.error(e)
            self.signals.status.emit(_('Fehler im Bilderkennungsprozess:\n{}').format(e))
        finally:
            # Block until we can safely access image watcher dict
            LOGGER.debug('QRunnable for %s acquires lock.', self.img_file.stem)
            self.lock.acquire()

            # Update processed status if image has not been removed
            if self.img_file.exists():
                self.signals.status.emit(_('Bilderkennung abgeschlossen für {}. Bildinhalte erkannt.').format(img_name))
                self.signals.result.emit(self.img_file)
            else:
                self.signals.status.emit(_('Bilderkennung abgeschlossen für {}. '
                                           '<i>Keine Bildinhalte erkannt.</i>').format(img_name)
                                         )
            self.lock.release()
            LOGGER.debug('QRunnable for %s released lock.', self.img_file.stem)

    def kill_process(self):
        if self.process:
            try:
                LOGGER.info('Attempting to kill Image content detection process.')
                self.process.kill()
                LOGGER.info('Image content detection process killed.')
            except Exception as e:
                LOGGER.error('Killing the Image content detection process failed!')
                LOGGER.error(e)


class CreatePSDFileSignals(QtCore.QObject):
    result = QtCore.pyqtSignal(str)
    status = QtCore.pyqtSignal(str)


class CreatePSDFile(QtCore.QRunnable):

    def __init__(self, psd_file, img_dir, mod_dir, status_callback, result_callback):
        super(CreatePSDFile, self).__init__()
        self.psd_file, self.img_dir, self.mod_dir = psd_file, img_dir, mod_dir
        self.psd_creation_module = Path(self.mod_dir) / 'maya_mod/run_create_psd.py'

        self.signals = CreatePSDFileSignals()
        self.signals.result.connect(result_callback)
        self.signals.status.connect(status_callback)

    def run(self):
        try:
            self.signals.status.emit(_('Erstelle PSD Datei {}').format(self.psd_file.name))
            process = run_module_in_standalone(
                self.psd_creation_module.as_posix(), self.psd_file.as_posix(), self.img_dir.as_posix(),
                Path(self.mod_dir).as_posix()
                )
            process.wait()
        except Exception as e:
            LOGGER.error(e)

        # Mark PSD creation as finished even if unsuccessful to get the job finished
        self.signals.result.emit(self.psd_file.name)
