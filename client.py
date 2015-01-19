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
        self.logger = logging.getLogger('CLIENT_INFO {}'.format(name))

    def __hash__(self):
        return hash(self.name)

    def addr(self) -> tuple:
        return self.ip, self.port

    def serialize(self) -> str:
        self.logger.debug('client info serialized: {} {} {}'
                          .format(self.name, self.ip, self.port))
        return json.dumps({'name': self.name, 'ip': self.ip, 'port': self.port})

    @staticmethod
    def deserialize(json_string):
        json_object = json.loads(json_string)
        return ClientInfo(json_object['name'], int(json_object['port']),
                          json_object['ip'])

    def __eq__(self, other):
        return self.name == other.name and \
            self.port == other.port

    def __ne__(self, other):
        return not self == other

    def __str__(self):
        return self.name

    def __repr__(self):
        return str(self)


class DataContainer:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


class Client(QtCore.QObject):
    new_message = QtCore.pyqtSignal(str)
    new_client = QtCore.pyqtSignal(str)
    client_deleted = QtCore.pyqtSignal(str)
    upload_request = QtCore\
        .pyqtSignal(str, str, str)  # filename, size, client name
    busy = QtCore.pyqtSignal()
    download_complete = QtCore.pyqtSignal(str)
    upload_complete = QtCore.pyqtSignal(str)

    def __init__(self, port: int, name: str):
        super().__init__()
        logging.basicConfig(filename='{}.txt'.format(name), level=logging.DEBUG,
                            filemode='w')
        self.logger = logging.getLogger('CLIENT')
        self.ip = '0.0.0.0'
        self.port = port
        self.name = name

        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, True)
        self.socket.bind((self.ip, self.port))
        self.logger.info('socket bind to {} {}'.format(self.ip, self.port))

        self.clients = set()
        self.clients.add(self.get_self_client_info())

        self.sources = {}

        self.stopped = False
        threading.Thread(target=self.receive_data).start()

        self.ping_time = 10

        def ping_clients():
            """
            Send ping message to connected clients
            """
            while not self.stopped:
                time.sleep(self.ping_time)
                with threading.Lock():
                    for client in self.clients:
                        if client == self.get_self_client_info():
                            continue
                        self.socket.sendto(b'PNG', client.addr())

        threading.Thread(target=ping_clients, daemon=True).start()

        self.alive_clients = {}

        def delete_dead_clients():
            """
            Delete dead clients.
            Use ping timestamp.
            """
            while not self.stopped:
                time.sleep(self.ping_time / 2)
                new_time = time.time()
                addrs = []
                with threading.Lock():
                    for addr, old_time in self.alive_clients.items():
                        if new_time - old_time > self.ping_time:
                            self.handle_deleting(DataContainer(address=addr))
                            addrs.append(addr)
                    for addr in addrs:
                        del self.alive_clients[addr]

        threading.Thread(target=delete_dead_clients, daemon=True).start()


    def get_self_client_info(self) -> ClientInfo:
        return ClientInfo(self.name, self.port)

    def request_clients(self, addr: tuple):
        self.socket.sendto(b'CIN', addr)

    def connect(self, ip: str, port: int):
        self.new_client.emit(self.name)
        address = (ip, port)
        self.logger.info('connecting to ({}, {})'.format(*address))
        self.request_clients(address)

    def on_receive(self, sock: socket.socket):
        """
        Handle raw data and wrap it with DataContainer
        """
        try:
            data, addr = sock.recvfrom(2 ** 16)
        except ConnectionResetError:
            return
        except OSError:
            return
        try:
            data = data.decode()
        except UnicodeDecodeError:
            self.logger.warning('error in decoding received data')
            return
        action = data[:3]
        data = data[3:]
        self.logger.debug('action: {}; addr: {}; data: {}'
                          .format(action, addr, data))
        dc = DataContainer(address=addr, action=action, data=data)
        self.call_handler(dc)

    def receive_data(self):
        """
        Main receiver.
        Just look at socket and if can read invoke self.on_receive method
        """
        while not self.stopped:
            can_read, _, _ = select.select([self.socket], [], [], 0.01)
            for conn in can_read:
                self.on_receive(conn)

    def call_handler(self, container: DataContainer):
        """
        Choose correct method to handle container.action
        """
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
            if case('ACP'):  # Accept download
                self.handle_upload(container)
                break
            if case():
                self.logger.warning('unknown action: {}'.format(container.action))
                break

    def handle_upload(self, container: DataContainer):
        """
        Upload file
        """
        def upload():
            sock = socket.socket()
            try:
                sock.connect((container.address[0], int(container.data)))
            except ValueError:
                self.logger.warning('wrong address to connect to upload file')
                del self.sources[container.address]

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

    def start_downloading(self, file_path: str, port: int):
        """
        Download file
        """
        sock = socket.socket()
        sock.bind(('0.0.0.0', port))
        sock.listen(1)

        def download():
            sock.settimeout(10)
            try:
                remote_socket, addr = sock.accept()
            except socket.timeout:
                self.logger.warning('timed out when trying download file')
                return
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
        try:
            filename, size = container.data.split('\n')
        except ValueError:
            self.logger.warning('wrong data in handle_upload_request')
            return
        self.upload_request.emit(filename, size, name)

    def accept_download(self, path: str, name: str):
        """
        This method invokes when user accept upload request
        """
        def find_available_port() -> int:
            """
            Find available port in range(30000, 40000)
            """
            min_port = 30000
            max_port = 40000
            if sys.platform == 'linux':
                command = 'netstat -an | grep tcp | grep {}'
            else:  # sys.platform == 'win32'
                command = 'netstat.exe -an | find "TCP" | find "{}"'
            port = None
            while port is None:
                tmp_port = random.randint(min_port, max_port)
                try:
                    subprocess.check_output(command.format(tmp_port),
                                            shell=True)
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
        """
        Ping handler.
        Update ping timestamp
        """
        self.logger.info('ping from {}'.format(container.address))
        self.alive_clients[container.address] = time.time()

    def handle_deleting(self, container: DataContainer):
        """
        Delete client
        """
        client_info = self.item_by_addr(container.address)
        self.logger.info('deleting {}'.format(client_info.name))
        with threading.Lock():
            self.clients.discard(client_info)
        self.client_deleted.emit(client_info.name)

    def delete_me(self):
        """
        Send request to delete itself and close socket
        """
        self.logger.info('delete me')
        for ci in self.clients:
            if ci == self.get_self_client_info():
                continue
            self.socket.sendto(b'DEL', ci.addr())
        self.stopped = True
        self.socket.close()

    def send_client_infos(self, container: DataContainer):
        """
        Send all client_infos to requester
        """
        self.logger.info('clients infos sent to {}'.format(container.address))
        msg = 'NCI' + '\n'.join(x.serialize() for x in self.clients)
        bin_msg = msg.encode()
        self.socket.sendto(bin_msg, container.address)

    def send_upload_request(self, source_path: str, dest_client_name: str):
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

        def controller():
            time.sleep(60)
            try:
                if self.sources[client.addr()] is not None:
                    del self.sources[client.addr()]
            except KeyError:
                pass

        threading.Thread(target=controller).start()

    def handle_client_infos(self, container: DataContainer):
        """
        Add all client_infos from container
        """
        for line in container.data.split('\n'):
            tmp_container = DataContainer(address=container.address,
                                          data=line)
            ci = self.add_client_info(tmp_container)
            if ci is None:
                continue
            self.send_client_info(self.get_self_client_info(), ci.addr())

    def item_by_addr(self, addr: tuple) -> ClientInfo:
        """
        Return client specified by address
        """
        for ci in self.clients:
            if ci.port == addr[1]:
                return ci
        return ClientInfo('unknown', 0)

    def item_by_name(self, name: str) -> ClientInfo:
        """
        Return client specified by name
        """
        for ci in self.clients:
            if ci.name == name:
                return ci
        return ClientInfo('unknown', 0)

    def recv_msg(self, container: DataContainer):
        self.logger.info('new message received')
        msg = "{}: {}".format(self.item_by_addr(container.address).name,
                              container.data)
        self.new_message.emit(msg)

    def send_msg(self, msg: str, private_list: list):
        self.logger.info('msg sent')
        for client in self.clients:
            if client == self.get_self_client_info():
                self.new_message.emit("<strong>{}</strong>: {}".format(self.name,
                                                                   msg))
                continue

            if len(private_list) == 0:
                bin_msg = b'MSG' + msg.encode()
                self.socket.sendto(bin_msg, client.addr())
            elif client.name in private_list:
                bin_msg = b'MSG' + ('<font color="red">{}</font>'
                                    .format(msg)).encode()
                self.socket.sendto(bin_msg, client.addr())

    def send_client_info(self, ci: ClientInfo, addr: tuple):
        """
        Send serialized client_info
        """
        self.logger.info('client info "{} {} {}" sent to {} {}'
                          .format(ci.name, ci.ip, ci.port, addr[0], addr[1]))
        self.socket.sendto(b'CLI' + ci.serialize().encode(), addr)

    def add_client_info(self, container: DataContainer) -> ClientInfo:
        """
        Deserialize and add new client and return it
        """
        try:
            ci = ClientInfo.deserialize(container.data)
        except ValueError:
            self.logger.warning('wrong data in add_client_info')
            return
        self.new_client.emit(ci.name)
        if ci.ip == 'localhost':
            ci.ip = container.address[0]
        with threading.Lock():
            if ci in self.clients:
                self.clients.discard(ci)
            self.clients.add(ci)
        self.logger.info('new client info added: {}'.format(ci))
        return ci
