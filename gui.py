import sys

__author__ = 'Галлям'

from PyQt5 import QtCore, QtWidgets, Qt
from client import Client


# noinspection PyUnresolvedReferences
class MainWindow(QtWidgets.QMainWindow):
    def initialise_client(self, name, port):
        if isinstance(port, str):
            port = int(port)
        self.client = Client(port, name)

        self.client.upload_request.connect(self.upload_request)
        self.client.busy.connect(self.busy)

    @staticmethod
    def busy():
        information = QtWidgets.QMessageBox()
        information.setWindowTitle('Information')
        information.setText('You are uploading file now.\r\n'
                            'Wait until upload complete.')
        information.addButton(QtWidgets.QMessageBox.Ok)
        information.setIcon(QtWidgets.QMessageBox.Information)
        information.setWindowModality(QtCore.Qt.ApplicationModal)
        information.exec()

    def upload_request(self, filename: str, size: str, name: str):
        request_window = QtWidgets.QMessageBox()
        request_window.setWindowTitle("Download?")
        request_window.setText("User name: %s\r\n"
                               "File name: %s\r\n"
                               "Size: %s\r\n"
                               "Do you want to continue?" % (name,
                                                             filename,
                                                             size))
        yes_button = request_window.addButton(QtWidgets.QMessageBox.Yes)
        request_window.addButton(QtWidgets.QMessageBox.No)
        request_window.setIcon(QtWidgets.QMessageBox.Information)
        request_window.setWindowModality(QtCore.Qt.ApplicationModal)
        request_window.exec()

        if request_window.clickedButton() == yes_button:
            fd = QtWidgets.QFileDialog()
            dir_url = fd.getExistingDirectoryUrl()
            self.client.accept_download(dir_url.path() + '/' + filename, name)
        else:
            pass

    def __init__(self, name: str=None, port: int=None):
        super().__init__()
        self.name = name
        self.port = port
        self.client = None

        self.privates = []

        self.setAcceptDrops(True)

        if name is None:
            self.get_name_and_port()
            pass
        else:
            self.main_init(name, port)

    def main_init(self, name: str, port: int):
        self.initialise_client(name, port)
        self.create_main_widget()
        self.initialise()
        self.showNormal()
        self.setFocus(QtCore.Qt.ActiveWindowFocusReason)

    def set_name(self, name: str):
        self.name = name

    def set_port(self, port: int):
        self.port = port

    def get_name_and_port(self):
        self.hide()
        getter = StartWindow()
        self.g = getter

        def on_click():
            name = getter.name_line_edit.text()
            port = int(getter.port_line_edit.text())
            self.main_init(name, port)

        getter.ok_button.clicked.connect(on_click)
        getter.ok_button.clicked.connect(getter.close)
        getter.show()

    def create_main_widget(self):
        central = QtWidgets.QWidget()
        central.setAcceptDrops(True)

        main_layout = QtWidgets.QVBoxLayout(central)

        msg_layout = QtWidgets.QHBoxLayout()
        send_btn = QtWidgets.QPushButton("&Send")

        msg = QtWidgets.QLineEdit()
        msg.returnPressed.connect(send_btn.click)

        def send_msg():
            message = msg.text()
            self.client.send_msg(message, self.privates.copy())
            self.privates.clear()

        send_btn.clicked.connect(send_msg)
        send_btn.clicked.connect(msg.clear)
        msg_layout.addWidget(msg)
        msg_layout.addWidget(send_btn)

        grid_layout = QtWidgets.QGridLayout()
        main_layout.addLayout(msg_layout)
        main_layout.addLayout(grid_layout)

        text = QtWidgets.QTextEdit()
        text.setReadOnly(True)
        self.client.new_message.connect(text.append)
        grid_layout.addWidget(text, 0, 0, 0, 1)

        clients_list = ClientsList()

        clients_list.setFixedWidth(74)
        self.client.new_client.connect(clients_list.addItem)

        def set_private(names: list):
            self.privates = names.copy()

        clients_list.private_with.connect(set_private)
        clients_list.upload_file.connect(self.client.upload)

        def del_client(name: str):
            match = clients_list.findItems(name, QtCore.Qt.MatchExactly)
            clients_list.takeItem(clients_list.row(match[0]))

        self.client.client_deleted.connect(del_client)
        grid_layout.addWidget(clients_list, 0, 1)

        clear_button = QtWidgets.QPushButton('&Reset')
        clear_button.clicked.connect(lambda: clients_list.clearSelection())
        grid_layout.addWidget(clear_button, 1, 1)

        self.setCentralWidget(central)

    def closeEvent(self, event):
        self.client.delete_me()
        event.accept()

    def initialise(self):
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
                self.client.connect(ip, port)

            ok = QtWidgets.QPushButton('OK')

            ip_line_edit.returnPressed.connect(ok.click)
            port_line_edit.returnPressed.connect(ok.click)

            ok.clicked.connect(on_click)
            main_layout.addWidget(ok)
            tmp.show()

        connect_action = QtWidgets.QAction('Connect', self)
        connect_action.triggered.connect(conn_to)
        main_toolbar.addAction(connect_action)


class ClientsList(QtWidgets.QListWidget):
    wrong_files_count = QtCore.pyqtSignal()
    private_with = QtCore.pyqtSignal(list)
    upload_file = QtCore.pyqtSignal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDropIndicatorShown(True)
        self.setDefaultDropAction(QtCore.Qt.CopyAction)
        self.setDragDropMode(QtWidgets.QAbstractItemView.DropOnly)
        self.setSelectionMode(QtWidgets.QAbstractItemView.MultiSelection)

    def selectionChanged(self, *args, **kwargs):
        if len(self.selectedItems()) == 0:
            return
        self.private_with.emit([item.text() for item in self.selectedItems()])

    def contextMenuEvent(self, event: Qt.QContextMenuEvent):

        index = self.indexAt(event.pos())
        if index.isValid():
            menu = QtWidgets.QMenu(self)
            name = index.data(QtCore.Qt.DisplayRole)
            upload_action = QtWidgets.QAction('Upload file', menu)

            def upload():
                w = QtWidgets.QFileDialog()
                url = w.getOpenFileUrl()[0]
                if url.path() != '':
                    self.upload_file.emit(url.path(), name)

            upload_action.triggered.connect(upload)
            menu.addAction(upload_action)
            menu.exec(event.globalPos())


# noinspection PyUnresolvedReferences
class StartWindow(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowModality(QtCore.Qt.ApplicationModal)
        port_line_edit = QtWidgets.QLineEdit()
        name_line_edit = QtWidgets.QLineEdit()

        self.port_line_edit = port_line_edit
        self.name_line_edit = name_line_edit

        port_layout = QtWidgets.QFormLayout()
        port_layout.addRow('Enter port:', port_line_edit)

        name_layout = QtWidgets.QFormLayout()
        name_layout.addRow('Enter your name:', name_line_edit)

        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.addLayout(port_layout)
        main_layout.addLayout(name_layout)

        ok = QtWidgets.QPushButton('OK')
        self.ok_button = ok

        port_line_edit.returnPressed.connect(ok.click)
        name_line_edit.returnPressed.connect(ok.click)

        main_layout.addWidget(ok)


if __name__ == '__main__':
    app = QtWidgets.QApplication([])
    main = MainWindow(*sys.argv[1:])
    sys.exit(app.exec_())
