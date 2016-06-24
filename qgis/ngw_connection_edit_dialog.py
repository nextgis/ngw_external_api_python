# -*- coding: utf-8 -*-

# -*- coding: utf-8 -*-
"""
/***************************************************************************
 NGW connection edit dialog

 NextGIS WEB API
                             -------------------
        begin                : 2014-10-31
        git sha              : $Format:%H$
        copyright            : (C) 2014 by NextGIS
        email                : info@nextgis.com
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""
import os
from urlparse import urlparse

from PyQt4 import uic
from PyQt4.QtCore import Qt, QObject, pyqtSignal, QThread
from PyQt4.QtGui import QDialog, QStringListModel, QCompleter, QDialogButtonBox
from ..core.ngw_connection_settings import NGWConnectionSettings
from ..core.ngw_resource_factory import NGWResourceFactory
from ..qgis.ngw_plugin_settings import NgwPluginSettings

__author__ = 'NextGIS'
__date__ = 'October 2014'
__copyright__ = '(C) 2014, NextGIS'

# This will get replaced with a git SHA1 when you do a git archive

__revision__ = '$Format:%H$'


FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'ngw_connection_edit_dialog_base.ui'))


class NGWConnectionEditDialog(QDialog, FORM_CLASS):
    """
    Dialog for editing NGW connection settings
    ::param
    ngw_connection_settings
    If None - new connections settings instance was return
    Else - fields will be filed from param

    ::return
    If accept, DialogInstance.ngw_connection_settings contains edited instance
    """
    def __init__(self, parent=None, ngw_connection_settings=None, only_password_change=False):
        super(NGWConnectionEditDialog, self).__init__(parent)

        self._default_server_suffix = ".nextgis.com"
        self.__user_try_accept = False
        self.__only_password_change = only_password_change

        self.setupUi(self)

        self.lbConnectionTesting.setVisible(False)
        self.buttonBox.button(QDialogButtonBox.Ok).setEnabled(False)

        if self.__only_password_change:
            self.buttonBox.button(QDialogButtonBox.Ok).setEnabled(True)
            self.leUrl.setEnabled(False)
            self.leName.setEnabled(False)

        self.completer_model = QStringListModel()
        completer = QCompleter()
        completer.setModel(self.completer_model)
        completer.setCompletionMode(QCompleter.UnfilteredPopupCompletion)
        self.leUrl.setCompleter(completer)

        self.cbAsGuest.stateChanged.connect(self.__cbAsGuestChecked)
        self.leUrl.textChanged.connect(self.__autocomplete_url)
        self.leUrl.textChanged.connect(self.__fill_conneection_name)
        self.leUrl.editingFinished.connect(self.__check_connection)
        self.leName.textChanged.connect(self.__name_changed_process)
        self.__user_change_connection_name = False
        self.leName.editingFinished.connect(self.__name_changed_finished)

        self.__cbAsGuestChecked(self.cbAsGuest.checkState())

        self.ngw_conn_sett = ngw_connection_settings

        if self.ngw_conn_sett is not None:
            self.leUrl.setText(self.ngw_conn_sett.server_url)
            self.leName.setText(self.ngw_conn_sett.connection_name)

            if self.ngw_conn_sett.username == "":
                self.cbAsGuest.setCheckState(Qt.Checked)
                self.leUser.setText("administrator")
            else:
                self.cbAsGuest.setCheckState(Qt.Unchecked)
                self.leUser.setText(self.ngw_conn_sett.username)
                self.lePassword.setText(self.ngw_conn_sett.password)
        else:
            self.leUser.setText("administrator")

    def __autocomplete_url(self, text):
        if not self.__only_password_change:
            self.buttonBox.button(QDialogButtonBox.Ok).setEnabled(False)

        text_complete = self._default_server_suffix

        if any(char in text for char in [':', '\\', '/']):
            return

        first_point_pos = text.find(self._default_server_suffix[0])
        if first_point_pos != -1:
            text_after_point = text[first_point_pos:]

            if text_complete.find(text_after_point) == 0:
                text_complete = text_complete[len(text_after_point):]
            else:
                return
        self.completer_model.setStringList([text + text_complete])
        self.__validate_fields()

    def __make_valid_url(self, url):
        o = urlparse(url)
        hostname = o.hostname
        if hostname is None:
            hostname = "http://"
            return hostname + url
        return url

    def __fill_conneection_name(self, url):
        if self.__user_change_connection_name is True:
            return

        url = self.__make_valid_url(url)

        o = urlparse(url)
        connection_name = o.netloc
        if connection_name.find(self._default_server_suffix) != -1:
            connection_name = connection_name.split('.')[0]

        self.leName.setText(connection_name)

    def __cbAsGuestChecked(self, state):
        self.leUser.setEnabled(state != Qt.Checked)
        self.lbUser.setEnabled(state != Qt.Checked)
        self.lePassword.setEnabled(state != Qt.Checked)
        self.lbPassword.setEnabled(state != Qt.Checked)

    def __name_changed_process(self, text):
        self.__validate_fields()

    def __name_changed_finished(self):
        self.__user_change_connection_name = True

    @property
    def ngw_connection_settings(self):
        return self.ngw_conn_sett

    def __validate_fields(self):
        if not self.__user_try_accept:
            return True

        validation_result = True
        url = self.leUrl.text()
        if url == "":
            self.leUrl.setStyleSheet("background-color: #FFCCCC")
            self.leUrl.setPlaceholderText(self.tr("Fill it!"))

            validation_result = False
        else:
            self.leUrl.setStyleSheet("background-color: None")
        name = self.leName.text()
        if name == "":
            self.leName.setStyleSheet("background-color: #FFCCCC")
            self.leName.setPlaceholderText(self.tr("Fill it!"))

            validation_result = False
        else:
            self.leName.setStyleSheet("background-color: None")

        return validation_result

    def __check_connection(self):
        name = "temp"
        url = self.leUrl.text()
        url = self.__make_valid_url(url)
        user = ""
        passward = ""

        ngw_conn_sett = NGWConnectionSettings(
            name,
            url,
            user,
            passward
        )

        pinger = NGWPinger(ngw_conn_sett)
        thread = QThread(self)
        thread.started.connect(pinger.run)

        pinger.finished.connect(thread.deleteLater)
        pinger.getResult.connect(self.__process_ping_result)

        self.lbConnectionTesting.setVisible(True)
        self.lbConnectionTesting.setStyleSheet("color: None")
        self.lbConnectionTesting.setText(self.tr("Connection test..."))
        thread.start()

        self.thread = thread
        self.pinger = pinger

    def __process_ping_result(self, ping_result):
        if ping_result is True:
            self.buttonBox.button(QDialogButtonBox.Ok).setEnabled(True)
            self.lbConnectionTesting.setText(self.tr("Connection success."))
            self.lbConnectionTesting.setStyleSheet("color: green")
        else:
            self.lbConnectionTesting.setText(self.tr("Connection failed! Please check the URL."))
            self.lbConnectionTesting.setStyleSheet("color: red")

    def accept(self):
        self.__user_try_accept = True
        if not self.__validate_fields():
            return

        url = self.leUrl.text()
        name = self.leName.text()

        url = self.__make_valid_url(url)

        user = ""
        passward = ""
        if self.cbAsGuest.checkState() == Qt.Unchecked:
            user = self.leUser.text()
            passward = self.lePassword.text()

        self.ngw_conn_sett = NGWConnectionSettings(
            name,
            url,
            user,
            passward)

        QDialog.accept(self)


class NGWPinger(QObject):
    getResult = pyqtSignal(bool)
    finished = pyqtSignal()

    def __init__(self, ngw_connection_settings):
        super(NGWPinger, self).__init__()
        self.__ngw_connection_settings = ngw_connection_settings

    def run(self):
        rsc_factory = NGWResourceFactory(
            self.__ngw_connection_settings
        )

        try:
            rsc_factory.get_ngw_verson()
            self.getResult.emit(True)
        except:
            self.getResult.emit(False)

        self.finished.emit()
