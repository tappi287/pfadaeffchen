#! usr/bin/python_3
"""
    Socket Server classes

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
from PyQt5 import QtCore
from time import time, sleep
import threading
import socket
import socketserver
from modules.app_globals import *

_BUFFER_SIZE = 2048


def recv_all(socket_obj, timeout=3):
    """ Loop thru receive until timeout """
    # total data partwise in an array
    total_data = list()

    begin = time()
    while 1:
        # if you got some data, then break after timeout
        if total_data or time() - begin > timeout:
            break

        # Receive something
        try:
            data = socket_obj.recv(_BUFFER_SIZE)

            if data:
                total_data.append(data.decode('utf-8'))
                begin = time()  # Reset timeout if we received something
            else:
                # sleep for sometime to indicate a gap
                sleep(0.01)
        except Exception as e:
            print(e)

    # join all parts to make final string
    return ''.join(total_data)


class MessageSignals(QtCore.QObject):
    message_signal = QtCore.pyqtSignal(str)
    start_recv_signal = QtCore.pyqtSignal()
    end_recv_signal = QtCore.pyqtSignal()


class MessageTcpHandler(socketserver.BaseRequestHandler):
    """
    BEWARE! This class will be instanced on every server request
    therefore you can not have multiple signal destinations.
    Use this handler class for exactly one server!
    """
    signals = None
    signal_destination = (None, None, None)

    def setup_signal_destination(self):
        if type(self.signal_destination) is tuple:
            msg_dest, recv_on, recv_off = self.signal_destination
            self.signals.message_signal.connect(msg_dest)
            self.signals.start_recv_signal.connect(recv_on)
            self.signals.end_recv_signal.connect(recv_off)
        else:
            self.signals.message_signal.connect(self.signal_destination)

    def setup(self):
        """ Called on every request before the handle method """
        self.signals = MessageSignals()
        self.setup_signal_destination()
        self.signals.start_recv_signal.emit()

    def handle(self):
        (host, port) = self.server.server_address

        # Recv the data
        data = recv_all(self.request, 1)

        print('{} received {} on port: {}'.format(host, data, port))

        # Emit a pyqtSignal containing the decoded data
        self.signals.message_signal.emit(data)
        self.signals.end_recv_signal.emit()


class WatcherTcpHandler(MessageTcpHandler):
    signal_destination = None


class ServiceSignals(QtCore.QObject):
    service_signal = QtCore.pyqtSignal(str, object, object)
    response_start = QtCore.pyqtSignal()
    response_end = QtCore.pyqtSignal()


class ServiceManagerTcpHandler(socketserver.BaseRequestHandler):
    """
    BEWARE! This class will be instanced on every server request
    therefore you can not have multiple signal destinations.
    Use this handler class for exactly one server!
    """
    signals = None
    signal_destination = (None, None, None)
    response_timeout = 15.0
    response = None

    def setup(self):
        """ Called on every request before the handle method """
        self.signals = ServiceSignals()
        service_msg, led_on, led_off = self.signal_destination
        self.signals.service_signal.connect(service_msg)
        self.signals.response_start.connect(led_on)
        self.signals.response_end.connect(led_off)
        self.response = None

    def respond(self, msg):
        """ Called from service manager """
        if type(msg) is str:
            self.response = msg.encode('utf-8')
        else:
            self.response = msg

    @staticmethod
    def get_client_name(client):
        client_name = 'Unknown'
        try:
            client_name = socket.gethostbyaddr(client[0])[0]
        except Exception as e:
            print(e)
            if type(client) is list and len(client):
                client_name = client[0]

        return client_name

    def handle(self):
        (host, port) = self.server.server_address

        # Receive the data
        self.signals.response_start.emit()
        data = recv_all(self.request, 3)
        print('{} received {} on port: {}'.format(host, data, port))

        # Forward the data to the service manager
        self.signals.service_signal.emit(data,  # Transfer request
                                         self.get_client_name(self.client_address),  # Transfer client host name
                                         self,  # Transfer TCPHandler class instance
                                         )
        # Wait for a response signal from service manager within timeout
        start_time = time()  # Timeout
        while start_time - time() < self.response_timeout:
            if self.response:
                self.request.sendall(self.response)
                break

        self.signals.response_end.emit()


class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    pass


def create_server_thread(address, handler):
    server = None
    try:
        server = ThreadedTCPServer(address, handler)

        # Start a thread with the server
        server_thread = threading.Thread(target=server.serve_forever)
        server_thread.start()
        print("Socket server loop running in " + server_thread.name)
    except OSError as e:
        print('Could not start internal message socket server.')
        print(e)

    return server


def run_message_server(signal_destination, address=SocketAddress.main):
    """
        Socket server that receives messages from external running processes
        and emits them to the GUI status browser
    """
    MessageTcpHandler.signal_destination = signal_destination
    print('Creating Main App socket server.')
    server = create_server_thread(address, MessageTcpHandler)
    return server


def run_watcher_server(signal_destination, address=SocketAddress.watcher):
    """
        Socket server that receives messages from external running processes
        and emits them to the Watcher GUI status browser
    """
    WatcherTcpHandler.signal_destination = signal_destination
    print('Creating Image Watcher socket server.')
    server = create_server_thread(address, WatcherTcpHandler)
    return server


def run_service_manager_server(signal_destination, address,):
    """
    Service manager socket server to handle client requests from the local network
    """
    ServiceManagerTcpHandler.signal_destination = signal_destination
    print('Creating Service Manager socket server.')
    server = create_server_thread(address, ServiceManagerTcpHandler)
    return server
