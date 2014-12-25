__author__ = 'Галлям'

from PyQt5 import QtCore, QtWidgets
from client import Client


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, name: str, port: int):
        super().__init__()
        self.initialise(name, port)

    def initialise(self, name: str, port: int):
        client = Client(port, name)

        central = QtWidgets.QWidget()

        vbox_layout = QtWidgets.QVBoxLayout(central)

        msg_layout = QtWidgets.QHBoxLayout()
        send_btn = QtWidgets.QPushButton("&Send")

        msg = QtWidgets.QLineEdit()
        msg.returnPressed.connect(send_btn.click)

        def send_msg():
            message = msg.text()
            client.send_msg(message)

        send_btn.clicked.connect(send_msg)
        msg_layout.addWidget(msg)
        msg_layout.addWidget(send_btn)

        vbox_layout.addLayout(msg_layout)

        text = QtWidgets.QTextEdit()
        text.setReadOnly(True)
        client.new_message.connect(text.append)
        vbox_layout.addWidget(text)

        self.setCentralWidget(central)

        main_toolbar = self.addToolBar('Main')

        def conn_to():
            tmp = QtWidgets.QWidget()
            ip_line_edit = QtWidgets.QLineEdit()
            port_line_edit = QtWidgets.QLineEdit()

            ip_layout = QtWidgets.QFormLayout()
            ip_layout.addRow('Enter ip:', ip_line_edit)

            port_layout = QtWidgets.QFormLayout()
            port_layout.addRow('Enter port:', port_line_edit)

            main_layout = QtWidgets.QVBoxLayout(tmp)
            main_layout.addLayout(ip_layout)
            main_layout.addLayout(port_layout)

            def on_click():
                ip = ip_line_edit.text()
                tmp.hide()
                port = int(port_line_edit.text())
                client.connect(ip, port)

            ok = QtWidgets.QPushButton('OK')
            ok.clicked.connect(on_click)
            main_layout.addWidget(ok)
            tmp.show()

        connect_action = QtWidgets.QAction('Connect', self)
        connect_action.triggered.connect(conn_to)
        main_toolbar.addAction(connect_action)
        self.show()


def create_main_window(port, name):
    print(port, name)
    main = MainWindow(name, port)
    main.show()
    return main


if __name__ == '__main__':
    main = None
    app = QtWidgets.QApplication([])
    getter = QtWidgets.QWidget()
    port_line_edit = QtWidgets.QLineEdit()
    name_line_edit = QtWidgets.QLineEdit()

    port_layout = QtWidgets.QFormLayout()
    port_layout.addRow('Enter port:', port_line_edit)

    name_layout = QtWidgets.QFormLayout()
    name_layout.addRow('Enter your name:', name_line_edit)

    main_layout = QtWidgets.QVBoxLayout(getter)
    main_layout.addLayout(port_layout)
    main_layout.addLayout(name_layout)

    def on_click():
        getter.hide()
        port = int(port_line_edit.text())
        name = name_line_edit.text()
        global main
        main = create_main_window(port, name)

    ok = QtWidgets.QPushButton('OK')
    ok.clicked.connect(on_click)
    main_layout.addWidget(ok)
    getter.show()
    app.exec_()
