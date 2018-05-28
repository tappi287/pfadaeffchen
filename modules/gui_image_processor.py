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
from time import sleep, time
from pathlib import Path
from PyQt5 import QtCore

from modules.detect_lang import get_translation
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


class ImageFileWatcher(QtCore.QThread):
    file_created_signal = QtCore.pyqtSignal(set, int)
    file_removed_signal = QtCore.pyqtSignal(set)
    status_signal = QtCore.pyqtSignal(str)
    psd_created_signal = QtCore.pyqtSignal()

    # Scan interval in seconds
    interval = 6

    # Thread Pool
    # increase thread timeout to 4 mins
    thread_timeout = 240000
    max_threads = 10

    # Scene file name
    scene_file_name = _('KeineSzenenDatei')

    def __init__(self, parent, output_dir, scene_file, mod_dir, logger):
        global LOGGER
        LOGGER = logger
        super(ImageFileWatcher, self).__init__(parent=parent)

        self.watch_active = False
        self.output_dir = Path(output_dir)

        if scene_file:
            self.scene_file_name = Path(scene_file).stem

        self.mod_dir = mod_dir
        self.watcher_img_dict = parent.img_files
        self.parent = parent

        # Called when rendering is finished
        self.create_psd_requested = False

        # Prepare thread pool
        self.thread_pool = QtCore.QThreadPool(parent=self)
        thread_count = max(1, min(self.max_threads, round(self.idealThreadCount() * 0.3)))
        self.thread_pool.setMaxThreadCount(thread_count)
        self.thread_pool.setExpiryTimeout(self.thread_timeout)

        self.status_signal.connect(self.parent.signal_receiver)
        self.file_created_signal.connect(self.parent.file_created)
        self.file_removed_signal.connect(self.parent.file_removed)
        self.psd_created_signal.connect(self.parent.psd_created)

        # Init message
        self.status_signal.emit(_('Bilderkennung verfügt über {0:02d} parallel ausführbare '
                                  'Threads auf dieser Maschine. '
                                  '{1:02d} Threads aktiv.')
                                .format(thread_count, self.thread_pool.activeThreadCount()))

        self.img_dict = dict()

    def reset(self):
        self.create_psd_requested = False
        del self.parent.img_files

    def deactivate_watch(self):
        self.watch_active = False
        self.status_signal.emit(_('Ordnerüberwachung eingestellt.'))

    def run(self):
        LOGGER.info('Image File Watcher starting.')
        if self.watch_active:
            self.initial_directory_index()

        while not self.isInterruptionRequested():
            # Process output folder
            if self.watch_active:
                self.watch_folder()

            # Check if rendering was finished and all images processed
            if self.create_psd_requested:
                self.create_psd()

            self.sleep(self.interval)

        LOGGER.error('Image File Watcher thread ending.')

    def watch_folder(self):
        self.img_dict = self.index_img_files(set_processed=False)
        self.report_changes(self.img_dict)
        self.watcher_img_dict = self.img_dict

    def initial_directory_index(self):
        # Index existing files on initial start
        self.watcher_img_dict = self.index_img_files(set_processed=True)
        LOGGER.info('Image File Watcher directory changed. Found %s already existing files.',
                    len(self.watcher_img_dict))
        self.status_signal.emit(_('Bild Daten Beobachter Verzeichnis gesetzt: '
                                '{0:02d} bereits exsitierende Dateien gefunden.')
                                .format(len(self.watcher_img_dict)))

    def create_psd_request(self):
        """ Called from mother ship """
        self.create_psd_requested = True

    def create_psd(self):
        """ Check that all images in the directory are processed and create layered PSD file """
        if self.thread_pool.activeThreadCount():
            # Threads detecting empty images are running, abort
            return

        img_dict = self.watcher_img_dict
        # TODO Detect zero images

        for __i in img_dict.items():
            img_key, img_file_dict = __i

            if not img_file_dict.get('processed'):
                # Some image(s) are not processed yet, skip
                break
        else:
            # Break never called - everything should be processed
            self.status_signal.emit(_('PSD wird erstellt.'))

            psd_file_name = self.scene_file_name + _('_Pfade.psd')
            psd_file = self.output_dir / psd_file_name

            LOGGER.debug('Starting PSD Thread: %s %s %s', psd_file, self.output_dir, self.mod_dir)
            create_psd_runner = CreatePSDFile(
                psd_file, self.output_dir, self.mod_dir, self.thread_status, self.psd_created
                )

            self.thread_pool.start(create_psd_runner)

            self.create_psd_requested = False

    def psd_created(self, psd_file):
        LOGGER.info('PSD File creation finished.')
        self.status_signal.emit(_('PSD Erstellung abgeschlossen für {}.').format(psd_file))
        self.psd_created_signal.emit()

    def change_output_dir(self, dir):
        """ Change watched directory and reset existing image entries
            Called from parent process.
        """
        # Reset process property
        del self.parent.img_files

        self.output_dir = Path(dir)

        if not self.output_dir.exists():
            self.output_dir.mkdir()

        self.watch_active = True
        self.status_signal.emit(_('Überwache Ordner: <b>{}</b>').format(self.output_dir.as_posix()))

        self.initial_directory_index()

    def change_scene_file(self, file):
        self.scene_file_name = Path(file).stem
        self.status_signal.emit(_('Szenendatei geändert zu: {}').format(self.scene_file_name))

    def index_img_files(self, set_processed=False):
        img_dict = dict()

        if not self.output_dir.exists():
            return img_dict

        for __img_file in self.output_dir.glob('*' + ImgParams.extension):
            if __img_file.stat().st_size < 200:
                continue

            # Image key
            img_key = __img_file.stem

            # Create image file dict entry
            img_dict.update({img_key: dict(path=__img_file)})
            # Update processed status
            img_dict.get(img_key).update(self.set_image_processed(__img_file, set_processed))

        return img_dict

    def report_changes(self, current_img_dict):
        self.file_created(current_img_dict)
        self.file_removed(current_img_dict)

    def file_created(self, img_dict):
        new_file_set = self.get_file_difference(old_dict=self.watcher_img_dict, new_dict=img_dict)

        if not new_file_set:
            return

        LOGGER.debug('Watcher found new files: %s', new_file_set)
        self.file_created_signal.emit(new_file_set, len(img_dict))

        for img_key in new_file_set:
            img_file = img_dict.get(img_key).get('path')

            if img_file:
                self.add_image_processing_thread(img_file)

    def add_image_processing_thread(self, img_file):
        # Create runnable and append to thread pool
        img_thread = ProcessImage(img_file, self.mod_dir, self.image_processing_result, self.thread_status)
        self.thread_pool.start(img_thread)

        max_threads = self.thread_pool.maxThreadCount()
        current_threads = self.thread_pool.activeThreadCount()

        self.status_signal.emit(_('<i>{0}</i> zur Bilderkennung eingereiht. '
                                  '{1:02d}/{2:02d} Threads aktiv.').format(img_file.name, current_threads, max_threads)
                                )

    def file_removed(self, img_dict):
        rem_file_set = self.get_file_difference(old_dict=img_dict, new_dict=self.watcher_img_dict)

        if not rem_file_set:
            return

        LOGGER.debug('Watcher found removed files: %s', rem_file_set)

        # Reset watcher img dict
        del self.parent.img_files
        self.watcher_img_dict = img_dict

        self.file_removed_signal.emit(rem_file_set)

    def set_image_processed(self, img_file: Path, processed: bool):
        existing_imgs = self.watcher_img_dict
        img_entry = existing_imgs.get(img_file.stem)

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

        return {'processed': processed}

    def image_processing_result(self, img_file: Path):
        """ Called from image processing thread """
        existing_imgs = self.watcher_img_dict

        file_dict = existing_imgs.get(img_file.stem)

        if file_dict:
            file_dict.update({'processed': True})

        # Update existing image dict
        self.watcher_img_dict = existing_imgs

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

    def __init__(self, img_file, mod_dir, result_callback, status_callback):
        super(ProcessImage, self).__init__()
        self.mod_dir = mod_dir
        self.img_file = img_file
        self.img_check_module = Path(self.mod_dir) / 'maya_mod/run_empty_img_check.py'

        # Prepare signals
        self.signals = ProcessImageSignals()
        self.signals.result.connect(result_callback)
        self.signals.status.connect(status_callback)

    def run(self):
        # Hopefully avoid race conditions while accessing files
        sleep(1)

        start_time = time()
        img_name = self.img_file.name

        while file_is_locked(self.img_file.as_posix()):
            if start_time - time() > self.file_lock_timeout:
                break

            print('File is locked ' + self.img_file.as_posix())
            self.signals.status.emit(_('Kein Schreibzugriff auf {}').format(img_name))
            sleep(2)

        # Run process in try-except to avoid re-running this QRunnable on process errors
        try:
            # Run Maya standalone to detect and delete empty image file
            LOGGER.debug('Running image detection process for %s', self.img_file.as_posix())
            process = run_module_in_standalone(
                self.img_check_module.as_posix(), self.img_file.as_posix(), self.mod_dir)
            process.wait()
        except Exception as e:
            LOGGER.error(e)
            self.signals.status.emit(_('Fehler im Bilderkennungsprozess:\n{}').format(e))
        finally:
            # Update processed status if image has not been removed
            if self.img_file.exists():
                self.signals.status.emit(_('Bilderkennung abgeschlossen für {}. Bildinhalte erkannt.').format(img_name))
                self.signals.result.emit(self.img_file)
            else:
                self.signals.status.emit(_('Bilderkennung abgeschlossen für {}. '
                                           '<i>Keine Bildinhalte erkannt.</i>').format(img_name)
                                         )


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
