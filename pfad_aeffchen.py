#! usr/bin/python_3
"""
    -------------
    Pfad Aeffchen
    -------------

    Basic path rendering functionality with a PyQt5 Gui

    This application should be run from Python 3.x interpreter while
    a few other modules will be run inside Autodesk Maya's mayapy Python 2.7 interpreter
    Most generic modules are compatible with 2.x and 3.x

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
import qt_ledwidget
from multiprocessing import Queue
from PyQt5 import QtWidgets, QtCore
from PyQt5.uic import loadUi

from modules.detect_lang import get_ms_windows_language, get_translation
from modules.gui_control_app import ControlApp
from modules.setup_log import setup_logging, setup_log_file, setup_log_queue_listener
from modules.setup_paths import get_current_modules_dir
from modules.app_globals import *

# get MS Windows language
os.environ.setdefault('LANGUAGE', get_ms_windows_language()[:2])

# translate strings
de = get_translation()
de.install()
_ = de.gettext

#TODO: Exception hook for main and image watcher process
#TODO: log image processor to Job log
#TODO:  Reduce psd layer count, compare target_look values with look values
#       create a dict of mappings target_look = source_look
#       then merge either renderlayers or images
#       less renderlayer would also greatly reduce render time

class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, app_class, mod_dir, version):
        super(MainWindow, self).__init__()
        self.app = app_class
        logging.root.setLevel(logging.ERROR)
        ui_file = os.path.join(mod_dir, UI_FILE_MAIN)
        loadUi(ui_file, self)
        logging.root.setLevel(logging.DEBUG)

        # Set version window title
        title = self.windowTitle()
        title = f'{title} - v{version}'
        self.setWindowTitle(title)

        # Add LED widget
        self.led_widget = qt_ledwidget.LedWidget(self, self.ledLayout, led_size=24)

        self.actionBeenden.triggered.connect(self.close)

        # Translate Window content
        self.window_translations()

    def window_translations(self):
        # Description label
        desc_str = _("{0}").format(DESC_STRING, DESC_EN_STR)
        self.label_desc.setText(desc_str)

        self.label.setText(_("Pfad zur CSB Datei *.csb oder zur MayaBinary *.mb angeben:"))
        self.label_2.setText(_("Pfad zum Render Ausgabe Verzeichnis angeben:"))
        self.label_3.setText(_("Gültige IP Subnetze"))
        self.label_4.setText(_("Maya Version:"))
        self.label_5.setText(_("Renderer:"))
        self.enableQueue.setText(_("Warteschlange abarbeiten - De-/ oder Aktiviert "
                                   "die weitere Bearbeitung von Jobs in der Warteschlange"))
        self.pathLabel.setText(_("Kein Verzeichnis festgelegt."))
        self.sceneLabel.setText(_("Keine Datei gewählt."))
        self.startBtn.setText(_("Lokalen Job hinzufügen"))
        self.startRenderService.setText(_("Render Service starten"))

        # Menu
        self.menuDatei.setTitle(_("Datei"))
        self.menuFenster.setTitle(_("Fenster"))
        self.actionBeenden.setText(_("Beenden"))
        self.actionToggleWatcher.setText(_("Bildprozess Fenster"))
        self.actionReport.setText(_("Report speichern"))

        # ToolBox labels
        tab_labels = [_("Einführung"), _("Lokaler Job"), _("Einstellungen")]
        for idx, item_text in enumerate(tab_labels):
            self.toolBox.setItemText(idx, item_text)

        # Job Manager column names
        column_names = ["#", _("Job Titel"), _("Szenendatei"), _("Ausgabeverzeichnis"), _("Progress"),
                        _("Klient"), _("Funktion"), _("Bestätigung")]
        header_item = self.widgetJobManager.headerItem()
        for idx, item_name in enumerate(column_names):
            if idx < header_item.columnCount():
                header_item.setText(idx, item_name)

    def closeEvent(self, close_event):
        close_event.ignore()
        self.app.quit()


class PfadAeffchenApp(QtWidgets.QApplication):
    scene_file_changed = QtCore.pyqtSignal(str)
    render_path_changed = QtCore.pyqtSignal(str)

    # Add job button timeout
    start_btn_timeout = QtCore.QTimer()
    start_btn_timeout.setSingleShot(True)
    start_btn_timeout.setInterval(800)

    # Automatic render service start
    start_render_service_timeout = QtCore.QTimer()
    start_render_service_timeout.setSingleShot(True)
    start_render_service_timeout.setInterval(2000)

    """ Main GUI Application """
    def __init__(self, mod_dir, version, logging_queue):
        super(PfadAeffchenApp, self).__init__(sys.argv)
        self.mod_dir, self.logging_queue = mod_dir, logging_queue

        # Create Main Window
        self.ui = MainWindow(self, mod_dir, version)
        self.ui.startBtn.setEnabled(False)
        self.ui.startBtn.pressed.connect(self.add_job_btn)
        self.ui.renderPathBtn.pressed.connect(self.open_dir_dialog)
        self.ui.sceneFileBtn.pressed.connect(self.open_file_dialog)
        self.ui.checkBoxCsbIgnoreHidden.toggled.connect(self.set_csb_import_hidden)
        self.ui.checkBoxMayaDeleteHidden.toggled.connect(self.set_maya_delete_hidden)

        # Local job GUI propertys
        self.scene_file = None
        self.render_path = None
        self.csb_ignore_hidden = '1'
        self.maya_delete_hidden = '1'
        self.scene_file_changed.connect(self.set_scene_file)
        self.render_path_changed.connect(self.set_render_path)

        self.start_btn_timeout.timeout.connect(self.enable_start_btn)

        # Prepare shutdown mechanism
        self.lastWindowClosed.connect(self.quit)
        self.aboutToQuit.connect(self.about_to_quit)

        # Run app controls in it's own class for easy resetting functionality
        self.control_app = ControlApp(self, self.ui, logging_queue)

        # Show Main Window
        self.ui.show()

        # Automatically start the render service(for autorun/startup compatibility)
        self.start_render_service_timeout.timeout.connect(self.ui.startRenderService.toggle)
        self.start_render_service_timeout.start()

    def reset_app(self):
        self.ui.statusBrowser.clear()
        self.control_app.__init__(self, self.ui, self.logging_queue)

    def set_csb_import_hidden(self, ignore_hidden):
        """ Set CSB Import option ignoreHiddenObject """
        if ignore_hidden:
            self.csb_ignore_hidden = '1'
        else:
            self.csb_ignore_hidden = '0'

        LOGGER.info('Local Job Option CSB Import option: ignoreHiddenObject=%s', self.csb_ignore_hidden)

    def set_maya_delete_hidden(self, maya_delete_hidden):
        """ Set Maya Layer creation process option maya_delete_hidden """
        if maya_delete_hidden:
            self.maya_delete_hidden = '1'
        else:
            self.maya_delete_hidden = '0'

        LOGGER.info('Local Job Option Maya delete hidden objects: maya_delete_hidden=%s', self.maya_delete_hidden)

    def set_scene_file(self, file_path):
        """ Set scene file in GUI for local job """
        if not file_path:
            return

        self.scene_file = file_path
        self.ui.sceneLabel.setText(file_path)

        if not self.render_path:
            self.render_path = os.path.dirname(file_path)

        self.validate_settings()

    def set_render_path(self, dir_path):
        if not dir_path:
            return

        self.render_path = dir_path
        self.validate_settings()

    def add_job_btn(self):
        """ Create local job"""
        self.ui.startBtn.setEnabled(False)
        self.start_btn_timeout.start()

        job_title = _('Lokaler Job')
        renderer = self.ui.comboBox_renderer.currentText()
        job_data = (job_title, self.scene_file, self.render_path, renderer,
                    self.csb_ignore_hidden, self.maya_delete_hidden)

        self.control_app.add_job_signal.emit(job_data)

    def enable_start_btn(self):
        self.control_app.enable_gui(True)
        self.ui.startBtn.setEnabled(True)

    def validate_settings(self):
        if self.scene_file:
            if not os.path.exists(self.scene_file):
                self.ui.startBtn.setEnabled(False)
                return
            if not self.ui.comboBox_version.currentText():
                return
            if not self.ui.comboBox_renderer.currentText():
                return

            self.control_app.update_watcher(self.scene_file)

        if self.render_path:
            if not os.path.exists(self.render_path):
                self.ui.startBtn.setEnabled(False)
                return

            self.render_path = os.path.abspath(self.render_path)
            self.ui.pathLabel.setText(self.render_path)

            self.control_app.update_watcher(output_dir=self.render_path)

        # Re-activate add job button after timeout
        self.start_btn_timeout.start()

    def open_file_dialog(self,
                         title=_('Szenendatei *.csb oder *.mb auswählen'),
                         file_filter=_('DeltaGen CSB, Maya binary (*.csb;*.mb)')):
        # User select save file dialog
        scene_file, file_type = QtWidgets.QFileDialog.getOpenFileName(self.ui, title, '.', file_filter)
        self.scene_file_changed.emit(scene_file)

        return scene_file, file_type

    def open_dir_dialog(self, title=_('Ausgabe Verzeichnis auswählen')):
        # User select save file dialog
        render_path = QtWidgets.QFileDialog.getExistingDirectory(self.ui, title, '.')
        self.render_path_changed.emit(render_path)

        return render_path

    def about_to_quit(self):
        # End watcher process and service manager
        self.control_app.quit_app()


def set_version(mod_dir):
    """ Write version info from pfad_aeffchen.cfg to resource directory
        to make it available to the installer version of the app aswell.
    """
    cfg_file = os.path.join(mod_dir, 'pfad_aeffchen.cfg')
    if not os.path.exists(cfg_file):
        LOGGER.info('%s does not exist.', cfg_file)
        # We're probably not in Dev environment
        return

    with open(cfg_file, 'r') as f:
        for line in f.readlines():
            if line.startswith('version'):
                # Version info found
                LOGGER.debug('Version info found.')
                version = line[line.find('=') + 1:]
                break
        else:
            LOGGER.debug('No Version info found.')
            # No version info found
            return

    # Write version info to resource directory
    version_info_file = os.path.join(mod_dir, 'res/version.txt')
    with open(version_info_file, 'w') as f:
        LOGGER.debug('Writing version to file %s.', version)
        f.write(version)


def read_version(mod_dir):
    version_info_file = os.path.join(mod_dir, 'res/version.txt')
    if not os.path.exists(version_info_file):
        return 'x.x'

    with open(version_info_file, 'r') as f:
        version = f.read()

    return version


def setup_aeffchen_log():
    global LOGGER
    setup_log_file(PFAD_AEFFCHEN_LOG_NAME, delete_existing_log_files=True)
    LOGGER = setup_logging('aeffchen_logger')


def main():
    # Setup log
    setup_aeffchen_log()

    # Prepare a multiprocess logging queue
    logging_queue = Queue(-1)

    # This will move all handlers from LOGGER to the queue listener
    log_listener = setup_log_queue_listener(LOGGER, logging_queue)
    # Start log queue listener in it's own thread
    log_listener.start()

    mod_dir = get_current_modules_dir()
    LOGGER.info('Modules directory: %s', mod_dir)

    # Set version file if we are in Dev environment
    set_version(mod_dir)

    # Get version info
    version = read_version(mod_dir)
    LOGGER.debug('Running version: %s', version)

    app = PfadAeffchenApp(mod_dir, version, logging_queue)
    result = app.exec_()
    LOGGER.debug('---------------------------------------')
    LOGGER.debug('Qt application finished with exitcode %s', result)

    log_listener.stop()
    logging.shutdown()
    sys.exit()


if __name__ == '__main__':
    """ 
        Only in debug! Nsis installer will start main() directly.
        Do not declare anything here!
    """
    main()
