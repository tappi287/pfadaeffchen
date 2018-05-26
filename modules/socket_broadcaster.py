#! usr/bin/python_3
""" Broadcast a service address on the local network """

import threading
from time import time
from socket import socket, AF_INET, SOCK_DGRAM, SOL_SOCKET, SO_BROADCAST, gethostname, gethostbyname_ex, timeout
from PyQt5 import QtCore

from maya_mod.socket_client import send_message
from modules.app_globals import SocketAddress


def get_valid_network_address(ip: str=None):
    """
    Iterates available network interfaces and returns
    the one that matches the pre-defined subpattern
    """
    hostname, aliaslist, ipaddrlist = gethostbyname_ex(gethostname())
    del hostname, aliaslist

    for valid_pattern in SocketAddress.valid_subnet_patterns:
        for ip in ipaddrlist:
            if ip.startswith(valid_pattern):
                break
        if ip:
            break

    if not ip:
        ip = '127.0.0.1'

    return ip


class AnnounceSignal(QtCore.QObject):
    do = QtCore.pyqtSignal()


class ServiceAnnouncer(threading.Thread):
    """ Announces the socket server address across the network """
    announce_interval = 15
    magic = SocketAddress.service_magic
    port = SocketAddress.service_port

    def __init__(self, logger, exit_event):
        super(ServiceAnnouncer, self).__init__()
        global LOGGER
        LOGGER = logger
        self.signals = AnnounceSignal()
        self.announce_signal = self.signals.do
        self.exit_event = exit_event

    def run(self):
        s = socket(AF_INET, SOCK_DGRAM)  # create UDP socket
        s.bind(('', 0))
        s.setsockopt(SOL_SOCKET, SO_BROADCAST, 1)  # this is a broadcast socket
        my_ip = get_valid_network_address()  # get our IP. Be careful if you have multiple network interfaces or IPs

        # MS Windows 10 workaround, use IP x.x.x.255 instead of b'<broadcast>'
        ip = get_valid_network_address()
        ip = ip.split('.')

        broadcast_ip = f'{ip[0]}.{ip[1]}.{ip[2]}.255'
        LOGGER.info('Announcing service %s at ip %s with %s', self.magic, my_ip, broadcast_ip)
        broadcast_ip.encode()

        send_message(_('Pfad Aeffchen Dienst wird unter der Adresse {}:{} angeboten').format(my_ip, self.port))

        while not self.exit_event.is_set():
            data = self.magic + my_ip
            data = data.encode(encoding='utf-8')

            s.sendto(data, (broadcast_ip, self.port))
            self.announce_signal.emit()

            self.exit_event.wait(timeout=self.announce_interval)

        s.close()


def get_service_address():
    search_timeout = 20  # Search for x seconds
    socket_timeout = 2
    service_address, data = None, None

    s = socket(AF_INET, SOCK_DGRAM)  # create UDP socket
    s.settimeout(socket_timeout)
    s.bind(('', SocketAddress.service_port))
    print('Listening to service announcement from ' + str(SocketAddress.service_port))

    s_time = time()

    while 1:
        try:
            data, addr = s.recvfrom(1024)  # wait for a packet
            data = data.decode(encoding='utf-8')
            print('Received: ' + data)
        except timeout:
            pass

        if data:
            if data.startswith(SocketAddress.service_magic):
                service_address = data[len(SocketAddress.service_magic):]
                print("Got service announcement from", data[len(SocketAddress.service_magic):])

        if (time() - s_time) > search_timeout or service_address:
            break

    s.close()
    return service_address


class FindService(threading.Thread):
    interval = 1
    timeout = 5
    service_address = None
    magic = SocketAddress.service_magic
    port = SocketAddress.service_port

    def __init__(self, exit_event: threading.Event, logger):
        super(FindService, self).__init__()
        global LOGGER
        LOGGER = logger
        self.exit_event = exit_event

    def run(self):
        while not self.exit_event.is_set():
            self.service_address = get_service_address()

            if self.service_address:
                break

            self.exit_event.wait(timeout=self.interval)
