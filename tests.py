import logging
from time import sleep

__author__ = 'Галлям'

import unittest
from client import Client, ClientInfo
import socket


class ClientTester(unittest.TestCase):
    def setUp(self):
        self.client_port = 6008
        self.client_address = ('localhost', self.client_port)
        self.client = Client(self.client_port, 'gall')
        self.socket = socket.socket(type=socket.SOCK_DGRAM)
        self.socket.bind(('localhost', 6001))

    def tearDown(self):
        try:
            self.client.delete_me()
        except OSError:
            pass
        self.socket.close()

    def test_correctly_connect(self):
        self.client.connect('localhost', 6001)
        data, _ = self.socket.recvfrom(2 ** 16)
        self.assertEqual(b'CIN', data)

    def test_do_not_crash_on_wrong_client_info(self):
        self.socket.sendto(b'CLIaghdafasdfa', self.client_address)
        sleep(0.1)
        self.assertEqual(1, len(self.client.clients))

    def test_add_right_client_info(self):
        self.socket.sendto(b'CLI{"name": "name", "ip": "localhost", '
                           b'"port": 6504}',
                           self.client_address)
        sleep(0.1)
        self.assertEqual(2, len(self.client.clients))
        self.assertEqual(ClientInfo('name', 6504),
                         self.client.item_by_name('name'))

    def test_correct_log_messages(self):
        with self.assertLogs(self.client.logger, logging.INFO) as cm:
            self.client.connect('localhost', 6000)
            self.client.send_client_info(ClientInfo('unknown', 1),
                                         ('localhost', 6000))
            self.socket.sendto(b'CLI' + str(ClientInfo('name', 2).serialize())
                               .encode(),
                               ('localhost', self.client_port))
            self.socket.sendto(b'PNG', self.client_address)
            self.socket.sendto(b'DEL', self.client_address)
            self.socket.sendto(b'CIN', self.client_address)
            sleep(0.1)
            self.client.delete_me()

        self.assertEqual(cm.output,
                         ['INFO:CLIENT:connecting to (localhost, 6000)',

                          'INFO:CLIENT:client info "unknown localhost 1" sent '
                          'to localhost 6000',

                          'INFO:CLIENT:new client info added: name',

                          'INFO:CLIENT:ping from (\'127.0.0.1\', 6001)',

                          'INFO:CLIENT:deleting unknown',

                          'INFO:CLIENT:clients infos sent to '
                          '(\'127.0.0.1\', 6001)',

                          'INFO:CLIENT:delete me'])

    def test_send_correct_clients(self):
        tmp_socket = socket.socket(type=socket.SOCK_DGRAM)
        tmp_socket.sendto(b'CLI{"name": "name", "ip": "localhost",'
                          b' "port": 5000}', self.client_address)
        tmp_socket.close()
        self.socket.sendto(b'CIN', self.client_address)
        data, _ = self.socket.recvfrom(2 ** 16)
        data = data[3:]
        data = data.decode()
        result = []
        for line in data.split('\n'):
            result.append(ClientInfo.deserialize(line))

        expected = [ClientInfo('gall', self.client_port),
                    ClientInfo('name', 5000, '127.0.0.1')]

        for client in result:
            self.assertTrue(client in expected)


if __name__ == "__main__":
    unittest.main()
  