#! usr/bin/python_3
"""
    -------------
    Pfad Aeffchen
    -------------

    Process to watch for rendererd image files and delete empty ones

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
import sys
import os
import logging
from gettext import translation
from datetime import datetime
from PyQt5 import QtWidgets, QtCore
from PyQt5.uic import loadUi

from modules.detect_lang import get_ms_windows_language, get_translation
from modules.setup_log import setup_logging, setup_log_file
from modules.socket_server import run_watcher_server
from maya_mod.socket_client import send_message
from modules.gui_image_processor import ImageFileWatcher
from modules.app_globals import *

# get one of supported languages
os.environ.setdefault('LANGUAGE', get_ms_windows_language()[:2])

# translate strings
de = get_translation()
de.install()
_ = de.gettext


class WatcherWindow(QtWidgets.QWidget):
    def __init__(self, app_class, mod_dir):
        super(WatcherWindow, self).__init__()

        self.app = app_class
        logging.root.setLevel(logging.ERROR)
        ui_file = os.path.join(mod_dir, UI_FILE_SUB)
        loadUi(ui_file, self)
        logging.root.setLevel(logging.DEBUG)

        title = _("Bilderkennungsprozess")
        self.setWindowTitle(title)

        desc_str = _("Überwacht den Ausgabeordner, entfernt leere Bilddateien "
                     "und erstellt abschließend eine PSD mit Ebenen.")
        self.labelDesc.setText(desc_str)

    def closeEvent(self, QCloseEvent):
        if not self.app.app_closing:
            QCloseEvent.ignore()
            send_message('COMMAND TOGGLE_WATCHER')
            return

        QCloseEvent.accept()


class WatcherApp(QtWidgets.QApplication):
    watcher_dir_changed = QtCore.pyqtSignal(str)
    watcher_scene_changed = QtCore.pyqtSignal(str)
    reset_signal = QtCore.pyqtSignal()
    request_psd = QtCore.pyqtSignal()
    deactivate_watch = QtCore.pyqtSignal()

    """ Main GUI Application """
    def __init__(self, mod_dir, render_path, scene_file, version):
        super(WatcherApp, self).__init__(sys.argv)

        self.app_ui = WatcherWindow(self, mod_dir)
        self.app_closing = False
        self.mod_dir, self.watch_dir, self.scene_file, self.version = mod_dir, render_path, scene_file, version

        self.server = run_watcher_server(self.signal_receiver)

        self.__img_files = dict(filename=dict(path='', processed=False))
        self.__img_files = dict()

        # Setup image file watcher
        self.image_watcher = None
        self.start_image_watcher()

        self.aboutToQuit.connect(self.about_to_quit)

        self.app_ui.show()

    @property
    def img_files(self):
        return self.__img_files

    @img_files.setter
    def img_files(self, val):
        self.__img_files.update(val)

    @img_files.deleter
    def img_files(self):
        self.__img_files = dict()

    def file_created(self, file_set, img_num):
        msg = _('Bilddatei erstellt: ') + str(file_set)
        send_message(msg)

        # Report total number of created images to main app
        send_message(f'COMMAND IMG_NUM {img_num:04d}')
        self.signal_receiver(msg)

    def file_removed(self, file_set):
        msg = 'Bilddatei entfernt: ' + str(file_set)
        send_message(msg)
        self.signal_receiver(msg)

    def psd_created(self):
        send_message(_('PSD Erstellung abgeschlossen.'))
        send_message('COMMAND IMG_JOB_FINISHED')

    def about_to_quit(self):
        self.app_closing = True
        LOGGER.debug('Watcher is shutting down Watcher socket server.')
        self.server.shutdown()
        self.server.server_close()

        LOGGER.debug('Watcher is shutting down Watcher Image File Watcher.')
        self.stop_image_watcher()

        self.app_ui.close()

    def start_image_watcher(self):
        self.image_watcher = ImageFileWatcher(self, self.watch_dir, self.scene_file, self.mod_dir, LOGGER)

        # Connect signals to thread
        self.request_psd.connect(self.image_watcher.create_psd_request)
        self.watcher_dir_changed.connect(self.image_watcher.change_output_dir)
        self.watcher_scene_changed.connect(self.image_watcher.change_scene_file)
        self.reset_signal.connect(self.image_watcher.reset)
        self.deactivate_watch.connect(self.image_watcher.deactivate_watch)

        # Start image watcher thread
        self.image_watcher.start(priority=QtCore.QThread.LowPriority)

    def stop_image_watcher(self):
        if self.image_watcher:
            if self.image_watcher.isRunning():
                self.image_watcher.requestInterruption()
                self.image_watcher.quit()

    def signal_receiver(self, msg):
        if msg.startswith('COMMAND'):
            socket_command = msg.replace('COMMAND ', '')

            if socket_command == 'HIDE_WINDOW':
                self.app_ui.hide()
            elif socket_command == 'SHOW_WINDOW':
                self.app_ui.show()
            elif socket_command == 'CLOSE':
                self.reset_signal.emit()
                self.quit()
            elif socket_command == 'ABORT':
                self.reset_signal.emit()
                self.deactivate_watch.emit()
            elif socket_command.startswith('VERSION'):
                self.version = socket_command.replace('VERSION ', '')
            elif socket_command.startswith('RENDER_PATH'):
                self.change_watch_dir(socket_command.replace('RENDER_PATH ', ''))
                self.reset_signal.emit()
            elif socket_command.startswith('SCENE_FILE'):
                self.change_watch_scene(socket_command.replace('SCENE_FILE ', ''))
            elif socket_command == 'REQUEST_PSD':
                self.request_psd.emit()

        current_time = datetime.now().strftime('(%H:%M:%S) ')
        self.app_ui.statusBrowser.append(current_time + msg)

    def change_watch_scene(self, scene):
        self.scene_file = scene
        self.watcher_scene_changed.emit(scene)

    def change_watch_dir(self, dir):
        if os.path.exists(dir):
            self.watch_dir = dir
            self.watcher_dir_changed.emit(self.watch_dir)


def start_watcher(mod_dir, render_path, scene_file, version):
    setup_log_file(WATCHER_PROCESS_LOG_NAME)
    global LOGGER
    LOGGER = setup_logging('watcher_logger')

    app = WatcherApp(mod_dir, render_path, scene_file, version)
    app.exec_()

    sys.exit()


if __name__ == '__main__':
    start_watcher()