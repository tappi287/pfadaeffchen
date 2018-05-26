#! python 2 and 3
"""
    Un-threaded socket client for Maya standalone modules

    MIT License

    Copyright (c) 2018 Stefan Tapper

    Permission is hereby granted, free of charge, to any person obtaining a copy
    of this software and associated documentation files (the "Software"), to deal
    in the Software without restriction, including without limitation the rights
    to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
    copies of the Software, and to permit persons to whom the Software is
    furnished to do so, subject to the following conditions:

    The above copyright notice and this permission notice shall be included in all
    copies or substantial portions of the Software.

    THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
    IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
    FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
    AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
    LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
    OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
    SOFTWARE.
"""
import socket
import threading
from modules.app_globals import *


def client(ip, port, message):
    s = socket.create_connection((ip, port), timeout=SocketAddress.time_out)
    s.sendall(message.encode('utf-8'))
    s.close()


def send_message(data, address=SocketAddress.main):
    """
    Create socket connection and send string data

    :param data: string data to send
    :param address: tuple (HOST-ADDRESS, PORT)
    :return: None
    """
    host, port = address
    try:
        client_thread = threading.Thread(target=client, args=(host, port, data))
        client_thread.start()
    except Exception as e:
        print(e)
