#! python 3
"""
    Threaded socket client

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
import socket
import threading
from modules.app_globals import *
from PyQt5 import QtCore


class SocketClientSignals(QtCore.QObject):
    finished = QtCore.pyqtSignal()


class SocketClient(threading.Thread):
    def __init__(self, address, message):
        super(SocketClient, self).__init__()
        self.ip, self.port = address
        self.msg = message
        self.signals = SocketClientSignals()
        self.finished = self.signals.finished

    def run(self):
        s = socket.create_connection((self.ip, self.port),
                                     timeout=SocketAddress.time_out)
        s.sendall(self.msg.encode('utf-8'))
        s.close()
        self.finished.emit()


class SendMessage(QtCore.QObject):
    send_started = QtCore.pyqtSignal()
    send_ended = QtCore.pyqtSignal()
    send_error = QtCore.pyqtSignal()

    def __init__(self):
        super(SendMessage, self).__init__()
        self.client_thread = None

    def do(self, data, address=SocketAddress.main):
        """
        Create socket connection and send string data

        :param data: string data to send
        :param address: tuple (HOST-ADDRESS, PORT)
        :return: None
        """
        host, port = address

        try:
            self.client_thread = SocketClient(address, data)
            self.client_thread.finished.connect(self.emit_finished)
            self.client_thread.start()
            self.send_started.emit()
        except Exception as e:
            print(e)
            self.send_error.emit()

    def emit_finished(self):
        self.send_ended.emit()

    def end_thread(self):
        if self.client_thread:
            if self.client_thread.isAlive():
                self.client_thread.join(timeout=SocketAddress.time_out)
