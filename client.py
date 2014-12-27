__author__ = 'Галлям'

import select
import socket
import json
import logging
import threading

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

    def __init__(self, port: int, name: str):
        super().__init__()
        logging.basicConfig(filename='%s.txt' % name, level=logging.DEBUG,
                            filemode='w')
        self.logger = logging.getLogger('CLIENT')
        self.ip = '0.0.0.0'
        self.port = port
        self.name = name

        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind((self.ip, self.port))
        self.logger.debug('socket bind to %s %s' % (self.ip, self.port))

        self.clients = set()
        self.clients.add(self.get_self_client_info())

        threading.Thread(target=self.receive_data, daemon=True).start()

    def get_self_client_info(self):
        return ClientInfo(self.name, self.port)

    def request_clients(self, addr: tuple):
        self.socket.sendto(b'CIN', addr)

    def connect(self, ip: str, port: int):
        address = (ip, port)
        self.logger.debug('connecting to (%s, %s)' % address)
        self.request_clients(address)

    def on_receive(self, sock: socket.socket):
        data, addr = sock.recvfrom(2 ** 16)
        data = data.decode()
        action = data[:3]
        data = data[3:]
        self.logger.debug('action: %s; addr: %s;, data: %s' %
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
            if case('CLI'):                             #  New ClientInfo
                self.add_client_info(container)
                break
            if case('MSG'):                             #  New message
                self.recv_msg(container)
                break
            if case('NCI'):                             #  New ClientInfos
                self.handle_client_infos(container)
                break
            if case('CIN'):                             # ClientInfo need
                self.send_client_infos(container)
                break
            if case('DEL'):                             # Delete
                self.handle_deleting(container)
                break
            if case():
                self.logger.debug('unknown action: %s' % container.action)
                break

    def handle_deleting(self, container: DataContainer):
        self.logger.debug('deleting %s' % self.item(container.address).name)
        self.clients.discard(self.item(container.address))

    def delete_me(self):
        self.logger.debug('delete me')
        for ci in self.clients:
            if ci.name == self.name:
                continue
            self.socket.sendto(b'DEL', ci.addr())

    def send_client_infos(self, container: DataContainer):
        msg = 'NCI' + '\n'.join(x.serialize() for x in self.clients)
        bin_msg = msg.encode()
        print(bin_msg)
        self.socket.sendto(bin_msg, container.address)

    def handle_client_infos(self, container: DataContainer):
        print(container.data)
        for line in container.data.split('\n'):
            ci = ClientInfo.deserialize(line)
            if ci.ip == 'localhost':
                ci.ip = container.address[0]
            self.clients.add(ci)
            self.send_client_info(self.get_self_client_info(), ci.addr())
            # self.socket.sendto(b'CLI' + self.get_self_client_info()
            #                    .serialize()
            #                    .encode(),
            #                    ci.addr())

    def item(self, addr: tuple) -> ClientInfo:
        for ci in self.clients:
            if ci.port == addr[1]:
                return ci
        return ClientInfo('unknown', 0)

    def recv_msg(self, container: DataContainer):
        self.logger.debug('new message received')
        msg = "%s: %s" % (self.item(container.address).name, container.data)
        self.new_message.emit(msg)

    def send_msg(self, msg: str):
        self.logger.debug('msg "%s" sent' % msg)
        bin_msg = b'MSG' + msg.encode()
        for client in self.clients:
            if client.name == self.name:
                self.new_message.emit("<strong>%s</strong>: %s" % (self.name,
                                                                   msg))
                continue
            self.socket.sendto(bin_msg, client.addr())

    def send_client_info(self, ci: ClientInfo, addr: tuple):
        self.logger.debug('client info "%s %s %s" sent to %s %s' %
                          (ci.name, ci.ip, ci.port, addr[0], addr[1]))
        self.socket.sendto(b'CLI' + ci.serialize().encode(), addr)

    def add_client_info(self, container: DataContainer):
        ci = ClientInfo.deserialize(container.data)
        if ci.ip == 'localhost':
            ci.ip = container.address[0]
        if ci in self.clients:
            self.clients.discard(ci)
        self.clients.add(ci)
