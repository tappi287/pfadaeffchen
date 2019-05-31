#! usr/bin/python_3
"""
    -------------
    Pfad Aeffchen
    -------------
    Creates the mayapy working processes for layer creation and rendering and catches the results

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
import re
import threading

from PyQt5 import QtCore

from maya_mod.start_command_line_render import run_command_line_render
from maya_mod.start_mayapy import run_module_in_standalone
from maya_mod.socket_client import send_message
from modules.app_globals import ImgParams


def log_subprocess_output(pipe, out_signal=None):
    """ Redirect subprocess output to logging so it appears in console and log file """
    for line in iter(pipe.readline, b''):
        #TODO fix logging accssessing log file
        try:
            line = line.decode(encoding='utf-8')
            line = line.replace('\n', '')
        except Exception as e:
            LOGGER.error('Error decoding process output: %s', e)

        if line:
            LOGGER.info('%s', line)

            if out_signal:
                if isinstance(line, str):
                    out_signal.emit(line)


class RunLayerCreationSignals(QtCore.QObject):
    finished = QtCore.pyqtSignal()
    failed = QtCore.pyqtSignal()
    update_job_status = QtCore.pyqtSignal(int)

    render_output_sig = QtCore.pyqtSignal(str)


class RunLayerCreationProcess(threading.Thread):
    def __init__(self,
                 # Logging instance
                 main_logger,
                 # Process Arguments
                 scene_file, render_path, module_dir=None,
                 ignore_hidden='1', delete_hidden='1', use_scene_settings='0',
                 version=None, use_renderer='',
                 # Callbacks
                 callback=None, failed_callback=None, status_callback=None):
        super(RunLayerCreationProcess, self).__init__()
        global LOGGER
        LOGGER = main_logger

        self.scene_file, self.render_path = scene_file, render_path
        self.module_dir, self.version = module_dir, version
        self.renderer, self.ignoreHidden = use_renderer, ignore_hidden
        self.delete_hidden, self.use_scene_settings = delete_hidden, use_scene_settings

        # Prepare signals
        self.signals = RunLayerCreationSignals()
        if callback:
            self.signals.finished.connect(callback)
        if failed_callback:
            self.signals.failed.connect(failed_callback)
        if status_callback:
            self.signals.update_job_status.connect(status_callback)

        self.signals.render_output_sig.connect(self.check_arnold_render_output)

        # Render scene file
        base_dir = os.path.dirname(self.scene_file)
        scene_name = os.path.splitext(os.path.basename(self.scene_file))[0]
        render_scene_name = scene_name + '_render.mb'
        self.render_scene_file = os.path.join(base_dir, render_scene_name)

        # Prepare workers
        self.process = None
        self.process_exitcode = None
        self.render_process = None
        self.render_process_exitcode = None

        self.event = threading.Event()

    def run(self):
        self.start_layer_creation()

        if not self.process:
            self.signals.failed.emit()

            LOGGER.error('Error starting Layer Creation module.')
            return

        # Set job status to scene creation
        self.signals.update_job_status.emit(1)

        # Wait until Layer creation finished or aborted
        while not self.event.is_set():
            self.event.wait()

        if self.process_exitcode != 0:
            self.signals.failed.emit()

            LOGGER.error('Layer creation failed or aborted.')
            return

        # Reset thread event
        self.event.clear()

        # Render in own thread to keep parent thread ready for abort signals
        self.start_batch_render()

        # Set job status to rendering
        self.signals.update_job_status.emit(2)

        # Wait until Batch rendering finished or aborted
        while not self.event.is_set():
            self.event.wait()

        if self.render_process_exitcode != 0:
            self.signals.failed.emit()
            return

        # Exit successfully
        self.signals.finished.emit()

    def start_layer_creation(self):
        module_file = os.path.join(self.module_dir, 'maya_mod/run_create_matte_layers.py')
        module_file = os.path.abspath(module_file)

        LOGGER.info('Starting maya standalone with: %s\n%s, %s, %s, %s, %s, %s, %s, %s pipe_output=%s',
                    os.path.basename(module_file),
                    self.scene_file, self.render_path, self.module_dir,
                    self.version, self.renderer,
                    self.ignoreHidden, self.delete_hidden, self.use_scene_settings, True)

        # Start process
        try:
            self.process = run_module_in_standalone(
                module_file,
                # Additional arguments for run_create_matte_layers.py:
                self.scene_file, self.render_path, self.module_dir, self.version, self.renderer,
                self.ignoreHidden, self.delete_hidden, self.use_scene_settings,
                pipe_output=True,     # Return a process that has output set to PIPE
                version=self.version  # mayapy version to use
                )
        except Exception as e:
            LOGGER.error(e)

        # Log STDOUT in own thread to keep parent thread ready for abort signals
        layer_log_thread = threading.Thread(target=self.process_log_loop)
        layer_log_thread.start()

    def process_log_loop(self):
        """ Reads and writes process stdout to log until process ends """
        with self.process.stdout:
            log_subprocess_output(self.process.stdout)

        LOGGER.info('Layer creation process stdout stream ended. Fetching exitcode.')
        self.process_exitcode = self.process.wait()
        LOGGER.info('Layer creation process ended with exitcode %s', self.process_exitcode)

        # Wake up parent thread
        self.event.set()

    def start_batch_render(self):
        """ Start batch render process and log to file and stdout """
        if not os.path.exists(self.render_scene_file):
            LOGGER.error('Layer creation did not create render scene file. Aborting.\n%s', self.render_scene_file)
            self.render_process_exitcode = -1
            return

        if self.renderer == 'arnold':
            img_ext = ImgParams.extension_arnold
        else:
            img_ext = ImgParams.extension

        res_x, res_y = 0, 0
        if self.use_scene_settings == '0':
            res_x, res_y = ImgParams.res_x, ImgParams.res_y

        try:
            self.render_process = run_command_line_render(
                self.render_scene_file, self.render_path, res_x, res_y,
                self.version, LOGGER,
                image_format=img_ext)
            LOGGER.info('Maya batch rendering started.')
        except Exception as e:
            LOGGER.error(e)

        # Log STDOUT in own thread to keep parent thread ready for abort signals
        render_log_thread = threading.Thread(target=self.render_process_log_loop)
        render_log_thread.start()

    def render_process_log_loop(self):
        """ Reads and writes process stdout to log until process ends """
        render_sig = None
        if self.renderer == 'arnold':
            render_sig = self.signals.render_output_sig

        with self.render_process.stdout:
            log_subprocess_output(self.render_process.stdout, render_sig)

        LOGGER.info('Maya batch process stdout stream ended. Fetching exitcode.')
        self.render_process_exitcode = self.render_process.wait()
        LOGGER.info('Maya batch process ended with exitcode %s', self.render_process_exitcode)

        # Wake up parent thread
        self.event.set()

    @staticmethod
    def check_arnold_render_output(line: str):
        """
            Receives batch render process output for rendering status
            Arnold prints "0% done" status
        """
        match = r'(\d+)(\%\sdone)'
        m = re.search(match, line)

        if m and m.groups():
            percent = m.groups()[0]
            if isinstance(percent, str) and percent.isdigit():
                p = int(percent)
                if not p % 10:  # Update on every 10 percent progress
                    img_num = 1 + round(p * 0.1)
                    send_message(f'COMMAND IMG_NUM {img_num}')

    def kill_process(self):
        if self.process:
            try:
                LOGGER.info('Attempting to kill Layer Creation process.')
                self.process.kill()
                LOGGER.info('Layer Creation process killed.')
            except Exception as e:
                LOGGER.error(e)

        if self.render_process:
            try:
                LOGGER.info('Attempting to kill Render process.')
                self.render_process.kill()
                LOGGER.info('Render process killed.')
            except Exception as e:
                LOGGER.error(e)
