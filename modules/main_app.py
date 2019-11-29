import os
import sys

from PyQt5 import QtCore, QtWidgets

from modules.detect_lang import get_translation
from modules.gui_control_app import ControlApp
from modules.main_ui import MainWindow

# translate strings
de = get_translation()
de.install()
_ = de.gettext


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
    def __init__(self, mod_dir, version, logger, logging_queue, log_listener):
        super(PfadAeffchenApp, self).__init__(sys.argv)
        self.mod_dir, self.logging_queue = mod_dir, logging_queue

        self.log_listener = log_listener
        self.logger = logger
        
        # Create Main Window
        self.ui = MainWindow(self, mod_dir, version)
        self.ui.startBtn.setEnabled(False)
        self.ui.startBtn.pressed.connect(self.add_job_btn)
        self.ui.renderPathBtn.pressed.connect(self.open_dir_dialog)
        self.ui.sceneFileBtn.pressed.connect(self.open_file_dialog)
        self.ui.checkBoxCsbIgnoreHidden.toggled.connect(self.set_csb_import_hidden)
        self.ui.checkBoxMayaDeleteHidden.toggled.connect(self.set_maya_delete_hidden)
        self.ui.checkBoxSceneSettings.toggled.connect(self.set_use_scene_settings)

        # Local job GUI propertys
        self.scene_file = None
        self.render_path = None
        self.csb_ignore_hidden = '1'
        self.maya_delete_hidden = '1'
        self.use_scene_settings = '0'
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

        self.logger.info('Local Job Option CSB Import option: ignoreHiddenObject=%s', self.csb_ignore_hidden)

    def set_maya_delete_hidden(self, maya_delete_hidden):
        """ Set Maya Layer creation process option maya_delete_hidden """
        if maya_delete_hidden:
            self.maya_delete_hidden = '1'
        else:
            self.maya_delete_hidden = '0'

        self.logger.info('Local Job Option Maya delete hidden objects: maya_delete_hidden=%s', self.maya_delete_hidden)

    def set_use_scene_settings(self, use_scene_settings):
        if use_scene_settings:
            self.use_scene_settings = '1'
        else:
            self.use_scene_settings = '0'

        self.logger.info('Local Job Option Use Scene Settings: use_scene_settings=%s', self.use_scene_settings)

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
                    self.csb_ignore_hidden, self.maya_delete_hidden, self.use_scene_settings)

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