#! usr/bin/python_3
"""
    -------------
    Pfad Aeffchen
    -------------

    Job Manager

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
import socket
import copy
import json
from datetime import datetime, timedelta
from PyQt5.QtCore import QThread, pyqtSignal, QTimer
from PyQt5.QtCore import Qt

from modules.job import Job
from modules.setup_log import setup_queued_logger
from modules.detect_lang import get_translation
from modules.setup_paths import get_user_directory, create_unique_render_path
from modules.app_globals import SocketAddress, JOB_DATA_EOS
from modules.socket_broadcaster import get_valid_network_address
from modules.socket_server import run_service_manager_server as rsm_server
from modules.app_globals import AVAILABLE_RENDERER

# translate strings
de = get_translation()
de.install()
_ = de.gettext


def copy_job(job):
    """ Create a flat copy of a job item """
    """
    # Copy main parameters
    job_title, scene_file, render_dir, renderer, client = job.title, job.file, job.render_dir, job.renderer, job.client

    # Create copy instance
    job_copy = Job(job_title, scene_file, render_dir, renderer, client)

    # Copy secondary parameters
    job_copy.remote_index, job_copy.total_img_num = job.remote_index, job.total_img_num
    # Copy property's
    job_copy.img_num = job.img_num
    job_copy.in_progress = job.in_progress
    job_copy.progress = job.progress
    job_copy.status = job.status
    """
    return copy.copy(job)


class ServiceManager(QThread):
    start_job_signal = pyqtSignal(object)
    abort_running_job_signal = pyqtSignal()
    force_psd_creation_signal = pyqtSignal()
    job_widget_signal = pyqtSignal(object)
    tcp_respond_signal = pyqtSignal(object)

    # LED signals
    response_led_start = pyqtSignal()
    response_led_stop = pyqtSignal()
    request_led_signal = pyqtSignal()

    # Green LED alive timer, signal the user we are alive
    alive_led_signal = pyqtSignal()

    job_active = False
    pickle_cache = b''
    transfer_cache = b''

    def __init__(self, control_app, app, ui, logging_queue):
        super(ServiceManager, self).__init__()
        global LOGGER
        LOGGER = setup_queued_logger(__name__, logging_queue)

        self.control_app, self.app, self.ui = control_app, app, ui

        self.job_working_queue = list()
        self.job_queue = list()
        self.empty_job = Job(_('Kein Job'), '', get_user_directory(), 'mayaSoftware')
        self.current_job = self.empty_job

        # Control app signals
        self.start_job_signal.connect(self.control_app.add_render_job)
        self.job_widget_signal.connect(self.control_app.update_job_widget)
        self.abort_running_job_signal.connect(self.control_app.abort_running_job)
        self.force_psd_creation_signal.connect(self.control_app.watcher_force_psd_creation)

        # Run service manager socket server
        self.server = None
        self.address = ('', 0)
        self.hostname = ''

        # Timer's must be created inside thread event loop, I guess...
        self.alive_led_timer = None
        self.validate_queue_timer = None

    def response_start_led(self):
        self.response_led_start.emit()

    def response_stop_led(self):
        self.response_led_stop.emit()

    def alive_led_blink(self):
        self.alive_led_signal.emit()

    def run(self):
        # Run service manager socket server
        self.address = (get_valid_network_address(), SocketAddress.service_port)
        sig_dest = (self.receive_server_msg, self.response_start_led, self.response_stop_led)
        self.server = rsm_server(sig_dest, self.address)

        # Setup queue validation
        self.validate_queue_timer = QTimer()
        self.validate_queue_timer.setTimerType(Qt.VeryCoarseTimer)
        self.validate_queue_timer.setInterval(600000)
        self.validate_queue_timer.timeout.connect(self.validate_queue)
        self.validate_queue_timer.start()

        # Connect Service Manager Server LED's
        self.response_led_start.connect(self.control_app.led_socket_recv_start)
        self.response_led_stop.connect(self.control_app.led_socket_recv_end)
        self.response_led_stop.connect(self.control_app.led_socket_send_end)
        self.request_led_signal.connect(self.control_app.led_socket_send_start)
        self.alive_led_signal.connect(self.control_app.alive_led_blink)

        # Setup alive LED
        self.alive_led_timer = QTimer()
        self.alive_led_timer.setInterval(1500)
        self.alive_led_timer.timeout.connect(self.alive_led_blink)
        self.alive_led_timer.start()

        try:
            self.hostname = socket.gethostbyaddr(self.address[0])[0]
        except Exception as e:
            LOGGER.error('%s', e)

        LOGGER.info('Service manager available at %s - %s', self.address[0], self.hostname)

        # Run thread event loop
        self.exec()

        LOGGER.info('Service manager received exit signal and is shutting down.')

        self.server.shutdown()
        self.server.server_close()

        LOGGER.info('Service manager Socket server shut down.')

    def validate_queue(self):
        """ Test if job items have expired """
        for job in self.job_queue:
            created = datetime.fromtimestamp(job.created)
            if (datetime.now() - created) > timedelta(hours=24):
                self.job_queue.remove(job)

    def prepare_queue_transfer(self, queue):
        """ Transfer the job queue to the client as serialized json dictonary """
        if not self.transfer_cache:
            # Create serialized queue byte encoded
            serialized_queue = self.serialize_queue(queue)
            serialized_queue = serialized_queue.encode(encoding='utf-8')
            # Cache the result
            self.cache_transfer_queue(serialized_queue)
        else:
            serialized_queue = self.transfer_cache

        response = serialized_queue + JOB_DATA_EOS

        if self.is_queue_finished():
            # All Jobs finished, tell clients to stop query's
            response = serialized_queue + b'Queue-Finished' + JOB_DATA_EOS
            LOGGER.debug('Service Manager adding Queue finished data to job transfer queue.')

        return response

    @staticmethod
    def serialize_queue(queue):
        """ Return the queued Job class instances as serialized json dictonary """
        job_dict = dict()

        for idx, job in enumerate(queue):
            job_dict.update(
                {idx: job.__dict__}
                )

        return json.dumps(job_dict)

    def cache_transfer_queue(self, serialized_queue):
        LOGGER.debug('Caching serialized job data queue in transfer cache.')
        self.transfer_cache = serialized_queue

    def invalidate_transfer_cache(self):
        if self.transfer_cache:
            LOGGER.debug('Invalidating transfer cache.')
            self.transfer_cache = b''

    def job_finished(self):
        """ Called from app if last job finished """
        self.job_active = False
        self.start_job()

    def start_job(self):
        """ Start the next job in the queue if no job is running """
        if not self.job_working_queue:
            return

        if not self.job_active:
            self.current_job = self.job_working_queue.pop(0)

            self.current_job.render_dir = create_unique_render_path(self.current_job.file, self.current_job.render_dir)

            self.start_job_signal.emit(copy_job(self.current_job))
            self.job_active = True

    def add_job(self, job_data, client: str=None):
        if type(job_data) is str:
            # Remove trailing semicolon
            if job_data.endswith(';'):
                job_data = job_data[:-1]
            # Convert to tuple
            job_data = tuple(job_data.split(';'))

        if not len(job_data) > 2:
            return False

        job_item = Job(*job_data)

        if not job_item.file or not job_item.render_dir:
            return False

        if client:
            job_item.client = client

        if not os.path.exists(job_item.file):
            return False
        if not os.path.exists(job_item.render_dir):
            return False

        self.invalidate_transfer_cache()
        self.job_working_queue.append(job_item)

        job_item.remote_index = len(self.job_queue)
        self.job_queue.append(job_item)
        self.job_widget_signal.emit(job_item)
        self.start_job()

        return True

    def cancel_job(self, job):
        if job.in_progress:
            LOGGER.info('Aborting currently running Job.')
            self.abort_running_job_signal.emit()

        job.set_canceled()

        # Remove from working queue
        if job in self.job_working_queue:
            self.job_working_queue.remove(job)

        self.invalidate_transfer_cache()

    def move_job(self, job, to_top=True):
        self.update_queue(job, self.job_working_queue, to_top)
        new_idx = self.update_queue(job, self.job_queue, to_top)

        if new_idx:
            job.remote_index = new_idx

        # Find job in progress and move it to top
        job_in_progress = None
        for __j in self.job_queue:
            if __j.in_progress:
                job_in_progress = __j
                break

        if job_in_progress:
            self.update_queue(job_in_progress, self.job_queue, True)

        self.update_control_app_job_widget()

        self.invalidate_transfer_cache()

    def update_control_app_job_widget(self):
        # Clear job widget
        self.job_widget_signal.emit(None)

        # Re-create job manager widget
        for __j in self.job_queue:
            self.job_widget_signal.emit(__j)

    def set_job_failed(self):
        self.current_job.set_failed()
        self.invalidate_transfer_cache()

    def set_job_canceled(self):
        self.current_job.set_canceled()
        self.invalidate_transfer_cache()

    def set_job_finished(self):
        self.current_job.set_finished()
        self.invalidate_transfer_cache()

    def set_job_status(self, status: int):
        self.current_job.status = status
        self.invalidate_transfer_cache()

    def set_job_status_name(self, status_name):
        self.current_job.status_name = status_name
        self.invalidate_transfer_cache()

    def set_job_img_num(self, img_num: int=0, total_img_num: int=0):
        if total_img_num:
            self.current_job.total_img_num = total_img_num
        if img_num:
            self.current_job.img_num = img_num
        self.invalidate_transfer_cache()

    @staticmethod
    def update_queue(job_item, list_queue, to_top):
        new_idx = None

        if to_top:
            insert_idx = 0
        else:
            insert_idx = len(list_queue)

        if job_item in list_queue:
            list_queue.remove(job_item)
            list_queue.insert(insert_idx, job_item)
            new_idx = list_queue.index(job_item)

        return new_idx

    def is_queue_finished(self):
        """ Return True if all jobs in the queue are finished """
        finished = False
        for job in self.job_queue:
            if job.status < 4:
                break
        else:
            # No unfinished jobs in the queue, mark queue finished
            if len(self.job_queue):
                # Only mark finished if there are actually jobs in the queue
                finished = True

        return finished

    def get_job_from_index(self, idx):
        job = None

        if len(self.job_queue) > idx:
            job = self.job_queue[idx]

        return job

    def receive_server_msg(self, msg, client_name=None, tcp_handler=None):
        """ Receive client requests from socket server and respond accordingly """
        self.request_led_signal.emit()
        if client_name:
            if msg != 'GET_JOB_DATA':
                LOGGER.debug('Service Manager received: "%s" from client %s', msg, client_name)
        else:
            LOGGER.info('Service manager received: %s', msg)

        response = 'Unknown command'

        # ----------- CLIENT CONNECTED ------------
        if msg.startswith('GREETING'):
            try:
                version = int(msg[-1:])
            except ValueError:
                version = 0

            if version:
                LOGGER.info('Client with version %s connected.', version)
                response = _('Render Dienst verfuegbar @ {} '
                             'Maya Version: {}').format(self.hostname, self.ui.comboBox_version.currentText())
            else:
                LOGGER.info('Invalid Client version connected!')
                response = _('Render Dienst verfuegbar @ {}<br>'
                             '<span style="color:red;">Die Client Version wird nicht unterstuetzt! '
                             'RenderKnecht Aktualisierung erforderlich!</span>').format(self.hostname)

        # ----------- TRANSFER RENDERER ------------
        elif msg == 'GET_RENDERER':
            response = 'RENDERER '

            # Convert list to ; separated string
            for __r in AVAILABLE_RENDERER:
                response += __r + ';'

            # Remove trailing semicolon
            response = response[:-1]

        # ----------- ADD REMOTE JOB ------------
        elif msg.startswith('ADD_JOB'):
            job_string_data = msg[len('ADD_JOB '):]
            msg_job_idx = len(self.job_queue)
            result = self.add_job(job_string_data, client_name)

            if result:
                response = _('Job #{0:02d} eingereiht in laufende Jobs.').format(msg_job_idx)
            else:
                response = _('<b>Job abgelehnt! </b><span style="color:red;">'
                             'Die Szenendatei oder das Ausgabeverzeichnis sind für den Server nicht verfügbar!</span>')

        # ----------- SEND JOB STATUS MESSAGE ------------
        elif msg == 'GET_STATUS':
            response = _('Momentan im Rendervorgang: '
                         '{0} - {1:03d} / {2:03d} Layer erzeugt.<br/>'
                         '{3:02d} Jobs in der Warteschlange.').format(
                self.control_app.current_job.title, self.control_app.current_job.img_num,
                self.control_app.current_job.total_img_num, len(self.job_working_queue)
                )

        # ----------- TRANSFER JOB QUEUE ------------
        elif msg == 'GET_JOB_DATA':
            # Send the queue as serialized JSON
            response = self.prepare_queue_transfer(self.job_queue)

        # ----------- MOVE JOB ------------
        elif msg.startswith('MOVE_JOB'):
            job_index, job, to_top = None, None, False

            if msg.startswith('MOVE_JOB_TOP'):
                job_index = msg[len('MOVE_JOB_TOP '):]
                to_top = True
            elif msg.startswith('MOVE_JOB_BACK'):
                job_index = msg[len('MOVE_JOB_BACK '):]
                to_top = False

            if job_index:
                job = self.get_job_from_index(int(job_index))

            if job:
                try:
                    self.move_job(job, to_top)
                    response = _('{} in Warteschlange bewegt.').format(job.title)
                except Exception as e:
                    LOGGER.error(e)
                    response = _('Job mit index {} konnte nicht bewegt werden.').format(job_index)

        # ----------- CANCEL JOB ------------
        elif msg.startswith('CANCEL_JOB'):
            job_index = msg[len('CANCEL_JOB '):]
            job = self.get_job_from_index(int(job_index))

            if job:
                self.cancel_job(job)
                response = _('{} wird abgebrochen.').format(job.title)
            else:
                response = _('Job mit index {} konnte nicht abgebrochen werden.').format(job_index)

        # ----------- FORCE PSD REQUEST ------------
        elif msg.startswith('FORCE_PSD_CREATION'):
            job_index = msg[len('FORCE_PSD_CREATION '):]
            job = self.get_job_from_index(int(job_index))

            if job:
                if job is self.current_job:
                    response = _('PSD Erstellung fuer Job {} wird erzwungen.').format(job.title)
                    self.force_psd_creation_signal.emit()
            else:
                response = _('Kann PSD Erstellung fuer Job {} nicht erzwingen.').format(job.title)

        if tcp_handler:
            self.tcp_respond_signal.connect(tcp_handler.respond)
            if type(response) is str:
                LOGGER.debug('Sending response: %s', response)
            else:
                LOGGER.debug('Sending response: transfer cache - %s', len(response))
            self.tcp_respond_signal.emit(response)
