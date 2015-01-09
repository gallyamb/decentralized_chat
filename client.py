import os
import random
import subprocess
import sys

__author__ = 'Галлям'

import select
import socket
import json
import logging
import threading
import time

from PyQt5 import QtCore

from switch_case import switch


class ClientInfo:
    def __init__(self, name: str, port: int, ip: str="localhost"):
        self.name = name
        self.port = port
        self.ip = ip
        self.logger = logging.getLogger('CLIENT_INFO %s' % name)

    def __hash__(self):
        return hash(self.name)

    def addr(self) -> tuple:
        return self.ip, self.port

    def serialize(self) -> str:
        self.logger.debug('client info serialized: %s %s %s' %
                          (self.name, self.ip, self.port))
        return json.dumps({'name': self.name, 'ip': self.ip, 'port': self.port})

    @staticmethod
    def deserialize(json_object):
        json_object = json.loads(json_object)
        return ClientInfo(json_object['name'], int(json_object['port']),
                          json_object['ip'])

    def __eq__(self, other):
        return self.name == other.name and \
            self.port == other.port

    def __ne__(self, other):
        return not self == other

    def __str__(self):
        return self.name


class DataContainer:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


class Client(QtCore.QObject):
    new_message = QtCore.pyqtSignal(str)
    new_client = QtCore.pyqtSignal(str)
    client_deleted = QtCore.pyqtSignal(str)
    upload_request = QtCore.pyqtSignal(str, str, str)  # filename, size, client name
    busy = QtCore.pyqtSignal()

    def __init__(self, port: int, name: str):
        super().__init__()
        logging.basicConfig(filename='%s.txt' % name, level=logging.DEBUG,
                            filemode='w')
        self.logger = logging.getLogger(__name__)
        self.ip = '0.0.0.0'
        self.port = port
        self.name = name

        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind((self.ip, self.port))
        self.logger.debug('socket bind to %s %s' % (self.ip, self.port))

        self.clients = set()
        self.clients.add(self.get_self_client_info())

        self.sources = {}

        threading.Thread(target=self.receive_data, daemon=True).start()

        self.ping_time = 10

        def ping_clients():
            while True:
                time.sleep(self.ping_time)
                with threading.Lock():
                    for client in self.clients:
                        if client.name == self.name:
                            continue
                        self.socket.sendto(b'PNG', client.addr())

        threading.Thread(target=ping_clients, daemon=True).start()

        self.alive_clients = {}

    def delete_dead_clients(self):
        new_time = time.time()
        addrs = []
        for addr, old_time in self.alive_clients.items():
            if new_time - old_time > self.ping_time:
                self.handle_deleting(DataContainer(**{'address': addr}))
                addrs.append(addr)
        for addr in addrs:
            del self.alive_clients[addr]

    def get_self_client_info(self):
        return ClientInfo(self.name, self.port)

    def request_clients(self, addr: tuple):
        self.socket.sendto(b'CIN', addr)

    def connect(self, ip: str, port: int):
        address = (ip, port)
        self.logger.debug('connecting to (%s, %s)' % address)
        self.request_clients(address)

    def on_receive(self, sock: socket.socket):
        try:
            data, addr = sock.recvfrom(2 ** 16)
        except ConnectionResetError:
            self.delete_dead_clients()
            return
        data = data.decode()
        action = data[:3]
        data = data[3:]
        self.logger.debug('action: %s; addr: %s; data: %s' %
                          (action, addr, data))
        dc = DataContainer(**{'address': addr,
                              'action': action,
                              'data': data})
        self.on_recv(dc)

    def receive_data(self):
        while True:
            can_read, _, _ = select.select([self.socket], [], [], 0.01)
            for conn in can_read:
                self.on_receive(conn)

    def on_recv(self, container: DataContainer):
        for case in switch(container.action):
            if case('CLI'):  # New ClientInfo
                self.add_client_info(container)
                break
            if case('MSG'):  # New message
                self.recv_msg(container)
                break
            if case('NCI'):  # New ClientInfos
                self.handle_client_infos(container)
                break
            if case('CIN'):  # ClientInfos need
                self.send_client_infos(container)
                break
            if case('DEL'):  # Delete
                self.handle_deleting(container)
                break
            if case('PNG'):  # Indicate that client alive (ping analog)
                self.set_alive(container)
                break
            if case('URQ'):  # Upload request
                self.handle_upload_request(container)
                break
            if case('URP'):  # Upload reply
                break
            if case('ACP'):  # Accept download
                self.handle_upload(container)
                break
            if case():
                self.logger.debug('unknown action: %s' % container.action)
                break

    def handle_upload(self, container: DataContainer):
        def upload():
            sock = socket.socket()
            sock.connect((container.address[0], int(container.data)))
            with open(self.sources[container.address], 'rb') as file:
                is_end = False
                while True:
                    _, can_write, _ = select.select([], [sock], [], 0.01)
                    if is_end:
                        break
                    for conn in can_write:
                        buf = file.read(2 ** 16)
                        if buf:
                            conn.send(buf)
                        else:
                            is_end = True
            del self.sources[container.address]

        threading.Thread(target=upload).start()

    @staticmethod
    def start_downloading(file_path, port: int):
        sock = socket.socket()
        sock.bind(('0.0.0.0', port))
        sock.listen(1)

        def download():
            remote_socket, addr = sock.accept()
            with open(file_path, 'wb') as file:
                is_end = False
                while True:
                    can_read, _, _ = select.select([remote_socket], [], [], 0.01)
                    if is_end:
                        break
                    for conn in can_read:
                        buf = conn.recv(2 ** 16)
                        if buf:
                            file.write(buf)
                        else:
                            is_end = True


        threading.Thread(target=download).start()

    def handle_upload_request(self, container: DataContainer):
        name = self.item_by_addr(container.address).name
        filename, size = container.data.split('\n')
        self.upload_request.emit(filename, size, name)

    def accept_download(self, path: str, name: str):
        def find_available_port() -> int:
            min_port = 30000
            max_port = 40000
            if sys.platform == 'linux':
                command = 'netstat -an | grep tcp | grep %s'
            else:  # sys.platform == 'win32'
                command = 'netstat -an | find "TCP" | find "%s"'
            port = None
            while port is None:
                tmp_port = random.randint(min_port, max_port)
                try:
                    subprocess.check_output(command % tmp_port, shell=True)
                except subprocess.CalledProcessError:
                    port = tmp_port
            return port

        if sys.platform == 'win32':
            path = path[1:]

        client = self.item_by_name(name)
        port = find_available_port()
        self.start_downloading(path, port)
        self.socket.sendto(b'ACP' + str(port).encode(), client.addr())

    def set_alive(self, container: DataContainer):
        self.alive_clients[container.address] = time.time()

    def handle_deleting(self, container: DataContainer):
        client_info = self.item_by_addr(container.address)
        self.logger.debug('deleting %s' % client_info.name)
        self.client_deleted.emit(client_info.name)
        with threading.Lock():
            self.clients.discard(client_info)

    def delete_me(self):
        self.logger.debug('delete me')
        for ci in self.clients:
            if ci.name == self.name:
                continue
            self.socket.sendto(b'DEL', ci.addr())

    def send_client_infos(self, container: DataContainer):
        self.logger.debug('clients infos sent to %s' % str(container.address))
        msg = 'NCI' + '\n'.join(x.serialize() for x in self.clients)
        bin_msg = msg.encode()
        self.socket.sendto(bin_msg, container.address)

    def upload(self, source_path: str, dest_client_name: str):
        client = self.item_by_name(dest_client_name)

        if sys.platform == 'win32':
            source_path = source_path[1:]

        if client.addr() in self.sources:
            self.busy.emit()
            return

        self.sources[client.addr()] = source_path
        filename = os.path.basename(source_path)
        size = os.path.getsize(source_path)
        self.socket.sendto(b'URQ' + filename.encode() + b'\n' +
                           str(size).encode(), client.addr())


    def handle_client_infos(self, container: DataContainer):
        for line in container.data.split('\n'):
            tmp_container = DataContainer(**{'address': container.address,
                                             'data': line})
            ci = self.add_client_info(tmp_container)
            self.send_client_info(self.get_self_client_info(), ci.addr())

    def item_by_addr(self, addr: tuple) -> ClientInfo:
        for ci in self.clients:
            if ci.port == addr[1]:
                return ci
        return ClientInfo('unknown', 0)

    def item_by_name(self, name: str) -> ClientInfo:
        for ci in self.clients:
            if ci.name == name:
                return ci
        return ClientInfo('unknown', 0)

    def recv_msg(self, container: DataContainer):
        self.logger.debug('new message received')
        msg = "%s: %s" % (self.item_by_addr(container.address).name, container.data)
        self.new_message.emit(msg)

    def send_msg(self, msg: str, private_list: list):
        self.logger.debug('msg "%s" sent' % msg)
        bin_msg = b'MSG' + msg.encode()
        for client in self.clients:
            if client.name == self.name:
                self.new_message.emit("<strong>%s</strong>: %s" % (self.name,
                                                                   msg))
                continue

            if len(private_list) == 0:
                self.socket.sendto(bin_msg, client.addr())
            elif client.name in private_list:
                self.socket.sendto(bin_msg, client.addr())

    def send_client_info(self, ci: ClientInfo, addr: tuple):
        self.logger.debug('client info "%s %s %s" sent to %s %s' %
                          (ci.name, ci.ip, ci.port, addr[0], addr[1]))
        self.socket.sendto(b'CLI' + ci.serialize().encode(), addr)

    def add_client_info(self, container: DataContainer) -> ClientInfo:
        ci = ClientInfo.deserialize(container.data)
        self.new_client.emit(ci.name)
        if ci.ip == 'localhost':
            ci.ip = container.address[0]
        with threading.Lock():
            if ci in self.clients:
                self.clients.discard(ci)
            self.clients.add(ci)
        return ci
