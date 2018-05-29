#! usr/bin/python_3
"""
    -------------
    Pfad Aeffchen
    -------------
    Control app represents all main funtionality

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
import threading
from datetime import datetime
from multiprocessing import Process
from functools import partial
from gettext import translation
from PyQt5 import QtCore, QtWidgets

from modules.detect_lang import get_translation
from modules.app_globals import AVAILABLE_RENDERER, SocketAddress, COMPATIBLE_VERSIONS
from modules.gui_image_watcher_process import start_watcher
from modules.gui_service_manager import ServiceManager
from modules.gui_create_process import RunLayerCreationProcess
from modules.job import Job
from modules.setup_log import JobLogFile
from modules.setup_paths import get_user_directory, get_maya_version
from modules.socket_broadcaster import ServiceAnnouncer
from modules.socket_client_3 import SendMessage
from modules.socket_server import run_message_server

# translate strings
de = get_translation()
_ = de.gettext


def get_available_versions():
    """ Create a list of available Maya versions on the current MS Windows machine """
    __available_versions = list()

    for version in COMPATIBLE_VERSIONS:
        # Returns the same version if it is available
        # returns any available version if the requested version is NOT available
        LOGGER.info('Searching Version %s', version)
        __maya_ver = get_maya_version(version)

        if __maya_ver == version:
            __available_versions.append(version)

    LOGGER.info('Found available Maya versions: %s', __available_versions)

    return __available_versions


def setup_combo_box(combo_box: QtWidgets.QComboBox, combo_items: list = list(), start_index: int = 0):
    """ Creates a combo box widget in given widget/item/column with given items/index/attributes """
    combo_box.addItems(combo_items)
    combo_box.setCurrentIndex(start_index)


def setup_widget_header(widget):
    maximum_width = 300
    header = widget.header()
    header.setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)

    # Calculate column width fitted to content and set resize mode to interactive
    # skip first column which should resize automagically
    # skip last column which has stretchLastSection enabled
    for column in range(1, header.count() - 1):
        header.setSectionResizeMode(column, QtWidgets.QHeaderView.ResizeToContents)
        width = min(header.sectionSize(column) + 20, maximum_width)
        header.setSectionResizeMode(column, QtWidgets.QHeaderView.Interactive)
        header.resizeSection(column, width)

    # Set sorting order to ascending by column 0: order
    widget.sortByColumn(0, QtCore.Qt.AscendingOrder)


def update_job_manager_widget(job, widget, btn_callback):
    """ Add a job to the JobManager widget """
    item_values = ['00', job.title, job.file, job.render_dir, job.status_name, job.client]
    item = QtWidgets.QTreeWidgetItem(widget, item_values)
    item.setText(0, f'{widget.topLevelItemCount():02d}')

    progress_bar = QtWidgets.QProgressBar(parent=widget)
    progress_bar.setAlignment(QtCore.Qt.AlignCenter)

    combo_box = QtWidgets.QComboBox(parent=widget)
    combo_box.addItems(job.combo_box_items)
    combo_box.setCurrentIndex(0)

    btn = QtWidgets.QPushButton()
    btn.setText(job.button_txt)
    btn.pressed.connect(partial(btn_callback, job, combo_box))

    widget.setItemWidget(item, 4, progress_bar)
    widget.setItemWidget(item, 6, combo_box)
    widget.setItemWidget(item, 7, btn)

    # Update progress bar
    job.update_progress()
    progress_bar.setFormat(job.status_name)
    progress_bar.setValue(job.progress)

    setup_widget_header(widget)


class LedControl:
    """ Control App helper class """
    def __init__(self, ui):
        self.ui = ui

    def alive_led_blink(self):
        self.led(2, 2, blink_count=2)

    def alive_job_blink(self):
        self.led(0, 2, blink_count=3)

    def led_socket_send_start(self):
        """ Activate green led"""
        self.led(2, 0)

    def led_socket_send_end(self):
        """ De-activate green led"""
        self.led(2, 1)

    def led_socket_recv_start(self):
        self.led(1, 0)

    def led_socket_recv_end(self):
        self.led(1, 1)

    def led_socket_send_error(self):
        """ Blink red 3 times"""
        self.led(0, 2, 3)

    def led_socket_announce(self):
        """ LED signal socket broadcast, red then yellow blink """
        self.led(0, 2)
        self.led(1, 2, timer=100)

    def led_all(self, forward=True):
        self.ui.led_widget.led_blink_all(forward=forward)

    def led(self, idx, action, blink_count=1, timer=0):
        """ Switch LED idx 0-On, 1-Off, 2-Blink * blink_count in timer msecs """
        if action == 0:
            self.ui.led_widget.led_on(idx)
        elif action == 1:
            self.ui.led_widget.led_off(idx)
        elif action == 2:
            self.ui.led_widget.led_blink(idx, blink_count, timer)


class ControlApp(QtCore.QObject, LedControl):
    # Service Manager Signals
    add_job_signal = QtCore.pyqtSignal(object)
    cancel_job_signal = QtCore.pyqtSignal(object)
    move_job_signal = QtCore.pyqtSignal(object, bool)
    update_job_widget_signal = QtCore.pyqtSignal()
    current_job_failed_signal = QtCore.pyqtSignal()
    current_job_canceled_signal = QtCore.pyqtSignal()
    current_job_finished_signal = QtCore.pyqtSignal()
    current_job_status_signal = QtCore.pyqtSignal(int)
    current_job_img_num_signal = QtCore.pyqtSignal(int, int)

    # Job finished timeout
    job_finished_timer = QtCore.QTimer()
    job_finished_timer.setSingleShot(True)
    job_finished_timer.setInterval(10000)

    # Red LED Job in progress timer, signal the user we have a Job running
    alive_job_timer = QtCore.QTimer()
    alive_job_timer.setInterval(1500)

    # Render service
    queue_next_job_signal = QtCore.pyqtSignal()
    current_job = None

    # Watcher process
    watcher = None
    # Service manager
    manager = None
    # Service announcer
    announcer = None

    def __init__(self, app, ui, logger):
        super(ControlApp, self).__init__(ui=ui)
        global LOGGER
        LOGGER = logger
        self.app, self.ui = app, ui

        self.scene_file = None
        self.render_path = None
        self.job_aborted = False
        self.mod_dir = self.app.mod_dir
        self.job_finished_timer.timeout.connect(self.job_finished)

        # Initialise Main Window
        self.ui.actionToggleWatcher.toggled.connect(self.toggle_watcher_window)
        self.ui.enableQueue.toggled.connect(self.start_queue)
        self.ui.startRenderService.toggled.connect(self.toggle_render_service)
        self.ui.actionReport.triggered.connect(self.save_status_report)
        self.ui.lineEditSubnet.editingFinished.connect(self.update_valid_ip_subnet_patterns)

        # Setup renderer ComboBox and set default to mayaSoftware 0
        setup_combo_box(self.ui.comboBox_renderer, AVAILABLE_RENDERER, 0)

        # Setup Maya version ComboBox and set default to highest version found
        available_maya_versions = get_available_versions()
        self.update_status(_('Installierte Maya Versionen: {}').format(available_maya_versions))
        setup_combo_box(self.ui.comboBox_version, available_maya_versions)

        # Setup socket server to receive status updates
        self.server = run_message_server(
            (self.update_status, self.led_socket_recv_start, self.led_socket_recv_end)
            )
        self.layer_creation_thread = None

        # Create default job
        self.empty_job = Job(_('Kein Job'), '', get_user_directory(), self.ui.comboBox_renderer.currentText())
        self.current_job = self.empty_job
        
        # Setup socket send
        self.socket_send = SendMessage()
        self.socket_send.send_started.connect(self.led_socket_send_start)
        self.socket_send.send_ended.connect(self.led_socket_send_end)
        self.socket_send.send_error.connect(self.led_socket_send_error)

        # GUI Feedback we are alive and running
        self.alive_job_timer.timeout.connect(self.alive_job_blink)

        self.init_network_render_service()

    def init_network_render_service(self):
        """ Start the image watcher process and the job service manager """
        if not self.render_path:
            self.render_path = get_user_directory()

        self.start_image_watcher_process()
        self.start_service_manager()

    def update_valid_ip_subnet_patterns(self, msg=''):
        ip_str = self.ui.lineEditSubnet.text()

        for ip in ip_str.split(';'):
            if len(ip.split('.')) == 3:
                if ip not in SocketAddress.valid_subnet_patterns:
                    SocketAddress.valid_subnet_patterns.append(ip)
                    msg += f'<i>{ip}</i>'

        if msg:
            self.update_status(_('Füge Benutzer IP Subnetze hinzu:<br>') + msg)

            # Disable Service announcer
            if self.announcer:
                if self.announcer.is_alive():
                    self.ui.startRenderService.toggle()
                    self.stop_service_manager()
                    self.update_status(_('Der Render Service muss neugestartet werden.'))
                    self.start_service_manager()

    def start_image_watcher_process(self):
        if self.watcher:
            if self.watcher.is_alive():
                self.update_watcher(self.current_job.file, self.current_job.render_dir)
                return
            else:
                self.socket_send.do('COMMAND CLOSE', SocketAddress.watcher)
                self.watcher.join()

        if self.current_job:
            render_path = self.current_job.render_dir
            scene_file = self.current_job.file
        else:
            render_path = self.render_path
            scene_file = self.scene_file

        # Start watcher process
        # on Win 7 x64 starting mayapy in threads from mayapy thread crashes Maya 2016.5 Ex2 Up2
        self.watcher = Process(target=start_watcher, args=(self.app.mod_dir,
                                                           render_path,
                                                           scene_file,
                                                           self.ui.comboBox_version.currentText(),
                                                           )
                               )
        self.watcher.start()

    def update_watcher(self, scene_file=None, output_dir=None):
        """ Update Image Watcher environment if it is running """
        if self.watcher:
            if scene_file:
                self.socket_send.do('COMMAND SCENE_FILE ' + scene_file, SocketAddress.watcher)
            if output_dir:
                self.socket_send.do('COMMAND RENDER_PATH ' + output_dir, SocketAddress.watcher)

    def add_render_job(self, job_object):
        """ Service Manager requests new job, scene file and render dir existence already confirmed """
        # This is a COPY of the actual service manager thread job class instance
        # Therefore we update our local copy -AND- signal all changes to the service
        # manager thread
        self.current_job = job_object

        # Set renderer
        for idx in range(0, self.ui.comboBox_renderer.count()):
            if self.ui.comboBox_renderer.itemText(idx) == self.current_job.renderer:
                self.ui.comboBox_renderer.setCurrentIndex(idx)

        msg = f'Starte {self.current_job.title} für <i>{self.current_job.file}</i> ' \
              f'mit {self.current_job.renderer}. Ausgabe: {self.current_job.render_dir}'
        self.update_status(msg)
        self.enable_gui(False)

        # Create job log file and add handler for it
        JobLogFile.setup(self.current_job.title, LOGGER)
        # Yellow LED blink
        self.led(1, 2, 2)

        self.start_queue()

    def start_queue(self):
        """ Start the queue of jobs if queue GUI switch is enabled """
        # Changing valid IP Subnet is no longer possible until restart
        self.ui.lineEditSubnet.setEnabled(False)

        if self.ui.enableQueue.isChecked():
            if self.current_job.status > 3:
                # Skip job if finished, failed, aborted
                self.job_finished()
                return

            # Set job status to scene loading/editing
            self.job_status(1)
            self.start_image_watcher_process()
            self.start_render_process()

    def job_failed(self):
        """ Called from unsuccessful render process """
        self.socket_send.do('COMMAND ABORT', SocketAddress.watcher)
        msg = f'<b>{self.current_job.title} fehlgeschlagen.</b> Ausgabeordner Überwachung wird abgebrochen.'
        self.update_status(msg)

        if self.job_aborted:
            LOGGER.debug('Setting Job %s as canceled %s.', self.current_job.title, self.job_aborted)
            self.current_job_canceled_signal.emit()
        else:
            LOGGER.debug('Setting Job %s as failed %s.', self.current_job.title, self.job_aborted)
            self.current_job_failed_signal.emit()

        self.job_aborted = False
        self.job_finished()

    def job_finished(self):
        """ Called from image watcher process if PSD Creation finished """
        self.save_status_report()

        # Reset job parameters
        self.current_job_finished_signal.emit()
        self.current_job = self.empty_job

        self.update_progress(reset=False)
        self.update_progress(reset=True)

        self.queue_next_job_signal.emit()

    def job_status(self, status):
        """ Update job status from creation thread """
        self.current_job_status_signal.emit(status)
        self.current_job.status = status
        self.update_progress()

    def watcher_create_psd(self):
        """ Finalize the job, continue detecting empty rendering results and create PSD """
        # Set job status to image detection
        self.job_status(3)

        if self.watcher:
            if self.watcher.is_alive():
                pass
            else:
                self.start_image_watcher_process()

        self.socket_send.do('COMMAND REQUEST_PSD', SocketAddress.watcher)

    def abort_running_job(self):
        """ Attempt to kill running processes for the current job """
        msg = f'<span style="color:red;"><b>{self.current_job.title} wurde vom Benutzer abgebrochen.</b></span>'
        self.update_status(msg)
        self.job_aborted = True
        self.job_status(6)

        if self.layer_creation_thread:
            if self.layer_creation_thread.is_alive():
                LOGGER.debug('Current Job canceled, trying to kill batch process.')
                self.layer_creation_thread.kill_process()
            else:
                LOGGER.debug('Current Job canceled, batch processed finished. Setting job as failed.')
                self.job_failed()
        else:
            LOGGER.debug('Current Job canceled, batch processed not present. Setting job as failed.')
            self.job_failed()

    def start_render_process(self):
        """ Start the layer creation process """
        args = (LOGGER,                         # Provide with the local logger
                self.current_job.file,          # Arg Scene file
                self.current_job.render_dir,    # Arg Render path
                self.mod_dir,                   # Arg Env / module directory
                self.current_job.ignore_hidden_objects,   # Arg CSB Import option ignoreHiddenObject
                self.ui.comboBox_version.currentText(),   # Arg Maya Version
                self.ui.comboBox_renderer.currentText(),  # Arg Maya renderer
                self.watcher_create_psd,        # Successfully finished Callback
                self.job_failed,                # Un-successfully finished Callback
                self.job_status,                # Update job status
                )

        self.layer_creation_thread = RunLayerCreationProcess(*args)
        self.layer_creation_thread.start()
        self.led(0, 0)

    def toggle_render_service(self):
        if self.ui.startRenderService.isChecked():
            self.led_all(forward=True)
            self.ui.startRenderService.setText(_('Render Service abschalten'))
            self.start_render_service()
        else:
            self.led_all(forward=False)
            self.ui.startRenderService.setText(_('Render Service einschalten'))
            self.stop_render_service()

    def start_render_service(self):
        """ Announce Render Service in the local network """
        if not self.announcer:
            # Announce own address on the network
            exit_event = threading.Event()
            self.announcer = ServiceAnnouncer(LOGGER, exit_event)
            self.announcer.announce_signal.connect(self.led_socket_announce)
            self.announcer.start()

    def stop_render_service(self):
        """ No longer announce Render Service in the local network """
        self.update_status(_('Render Service wird nicht mehr im Netzwerk angeboten.'))
        # End service announcer
        if self.announcer:
            if self.announcer.is_alive():
                LOGGER.debug('Shutting down service announcer.')
                self.announcer.exit_event.set()
                self.announcer.join(timeout=10)
                LOGGER.debug('Service announcer shut down.')
                self.announcer = None

    def start_service_manager(self):
        """
        Start service manager thread that handles all client communication and
        job creation.
        """
        LOGGER.info('Starting Service manager.')
        # Setup service manager
        self.manager = ServiceManager(self, self.app, self.ui, LOGGER)
        self.queue_next_job_signal.connect(self.manager.job_finished)

        self.add_job_signal.connect(self.manager.add_job)
        self.move_job_signal.connect(self.manager.move_job)
        self.cancel_job_signal.connect(self.manager.cancel_job)
        self.update_job_widget_signal.connect(self.manager.update_control_app_job_widget)
        self.current_job_failed_signal.connect(self.manager.set_job_failed)
        self.current_job_canceled_signal.connect(self.manager.set_job_canceled)
        self.current_job_finished_signal.connect(self.manager.set_job_finished)
        self.current_job_status_signal.connect(self.manager.set_job_status)
        self.current_job_img_num_signal.connect(self.manager.set_job_img_num)

        self.manager.start()

    def stop_service_manager(self):
        # End service manager
        if self.manager:
            if self.manager.isRunning():
                LOGGER.debug('Shutting down Service Manager.')
                self.manager.exit()
                self.manager.wait(msecs=15000)

    def update_status(self, status_msg):
        """ Receive socket messages """
        if status_msg.startswith('COMMAND'):
            self.led(1, 2)  # Blink yellow
            self.led(2, 2, timer=100)  # Blink green
            socket_command = status_msg.replace('COMMAND ', '')

            if socket_command == 'TOGGLE_WATCHER':
                self.ui.actionToggleWatcher.toggle()

            elif socket_command.startswith('LAYER_NUM'):
                # Update number of images to render (+1 for masterLayer)
                total_img_num = int(socket_command[len('LAYER_NUM '):]) + 1
                self.current_job_img_num_signal.emit(0, total_img_num)
                self.current_job.total_img_num = total_img_num
            elif socket_command.startswith('IMG_NUM'):
                # Update number of created images
                img_num = int(socket_command[len('IMG_NUM '):])
                self.current_job_img_num_signal.emit(img_num, 0)
                self.current_job.img_num = img_num
                self.update_progress()

            elif socket_command == 'CREATE_PSD':
                self.watcher_create_psd()

            elif socket_command == 'IMG_JOB_FINISHED':
                status_msg = _('<b>{} fertiggestellt. PSD Datei erstellt.</b>').format(self.current_job.title)
                self.job_finished_timer.start()

        current_time = datetime.now().strftime('(%H:%M:%S) ')
        self.ui.statusBrowser.append(current_time + status_msg)

    def update_progress(self, reset=False):
        """ Update GUI with current job progress """
        if reset or not self.current_job:
            self.ui.progressBar.setFormat('')
            self.ui.progressBar.setValue(0)
            self.led(0,1)
            return

        self.ui.progressBar.setFormat(f'{self.current_job.title} - '
                                      f'{self.current_job.img_num:03d} / {self.current_job.total_img_num:03d} - '
                                      f'{self.current_job.status_name}')

        # Indicate Job activity on red LED
        if self.current_job.in_progress:
            self.alive_job_timer.start()
        else:
            self.alive_job_timer.stop()

        self.ui.progressBar.setValue(self.current_job.progress)
        self.update_job_widget_signal.emit()

    def update_job_widget(self, job):
        """ Called from Service Manager thread """
        if job is None:
            self.ui.widgetJobManager.clear()
            return

        # Add job to widget
        update_job_manager_widget(job, self.ui.widgetJobManager, self.job_widget_button)

    def job_widget_button(self, job=None, combo_box=None):
        """ Job widget button """
        if not job or not self.manager or not combo_box:
            return

        job_request = combo_box.currentIndex()

        if job_request == 0:
            # Move to top of queue
            self.move_job_signal.emit(job, True)
        elif job_request == 1:
            # Move to end of queue
            self.move_job_signal.emit(job, False)
        elif job_request == 2:
            # Cancel job
            self.cancel_job_signal.emit(job)

        LOGGER.debug('Job button request: %s - %s', job.title, job_request)

    def save_status_report(self):
        # Close job log file handle and save content for report
        JobLogFile.finish(LOGGER)

        if not os.path.exists(self.current_job.render_dir):
            return

        # Report file path
        report_file = os.path.join(self.current_job.render_dir, 'report.html')
        # Append job log to report
        self.ui.statusBrowser.append(JobLogFile.text_report)
        html_data = str(self.ui.statusBrowser.toHtml())

        # Clear console
        try:
            sys.stdout.flush()
        except Exception as e:
            LOGGER.error(e)

        # Write report
        try:
            with open(report_file, 'w') as f:
                f.write(html_data)
        except Exception as e:
            LOGGER.error(e)
        finally:
            self.ui.statusBrowser.clear()

    def toggle_watcher_window(self, toggle_state):
        if not self.watcher:
            return

        if self.watcher.is_alive():
            if not toggle_state:
                self.socket_send.do('COMMAND HIDE_WINDOW', SocketAddress.watcher)
            else:
                self.socket_send.do('COMMAND SHOW_WINDOW', SocketAddress.watcher)

    def enable_gui(self, enable: bool):
        for gui in [self.ui.sceneFileBtn, self.ui.renderPathBtn, self.ui.comboBox_renderer,
                    self.ui.comboBox_version, self.ui.startBtn]:
            gui.setEnabled(enable)

    def quit_app(self):
        # End service announcer
        self.stop_render_service()
        self.update_status(_('Render Service beendet.'))

        # End service manager
        self.stop_service_manager()
        self.update_status(_('Service Manager beendet.'))

        # Wait for socket send thread to finish if running
        LOGGER.debug('Shutting down socket send thread.')
        self.socket_send.end_thread()
        self.update_status(_('Socket Senden Server beendet.'))

        # End socket server
        if self.server:
            LOGGER.debug('Shutting down socket message server.')
            self.server.shutdown()
            LOGGER.debug('Socket message server shut down.')
            self.update_status(_('Socket Empfangs Server beendet.'))

        # End watcher process
        if self.watcher:
            if self.watcher.is_alive():
                LOGGER.debug('Shutting down image processing server.')
                self.socket_send.do('COMMAND CLOSE', SocketAddress.watcher)
                self.watcher.join()
                LOGGER.debug('Image processing server shut down.')
                self.update_status(_('Bild Beobachter beendet.'))
