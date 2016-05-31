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
from PyQt4.QtCore import Qt
from PyQt4.QtGui import QDialog
from ..core.ngw_connection_settings import NGWConnectionSettings

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
    def __init__(self, parent=None, ngw_connection_settings=None):
        super(NGWConnectionEditDialog, self).__init__(parent)
        self.setupUi(self)
        # self.setFixedSize(self.size())

        self.cbAsGuest.stateChanged.connect(self.__cbAsGuestChecked)
        self.lbAdvancedSettings.linkActivated.connect(self.__advancedSettingsLinkActivate)

        self.__cbAsGuestChecked(self.cbAsGuest.checkState())

        self.ngw_conn_sett = ngw_connection_settings

        self.__advancedSettingsShown = False
        if self.ngw_conn_sett is not None:
            o = urlparse(self.ngw_conn_sett.server_url)
            if o.hostname.find("nextgis.com") != -1:
                self.leWebGIS.setText(o.hostname.split('.')[0])
            else:
                self.__advancedSettingsShown = True
                self.leName.setText(self.ngw_conn_sett.connection_name)
                self.leUrl.setText(self.ngw_conn_sett.server_url)

            if self.ngw_conn_sett.username == "":
                self.cbAsGuest.setCheckState(Qt.Checked)
                self.leUser.setText("administrator")
            else:
                self.cbAsGuest.setCheckState(Qt.Unchecked)
                self.leUser.setText(self.ngw_conn_sett.username)
                self.lePassword.setText(self.ngw_conn_sett.password)
        else:
            self.leUser.setText("administrator")

        self.__showHideAdvancedSettings()

    def __cbAsGuestChecked(self, state):
        self.leUser.setEnabled(state != Qt.Checked)
        self.lbUser.setEnabled(state != Qt.Checked)
        self.lePassword.setEnabled(state != Qt.Checked)
        self.lbPassword.setEnabled(state != Qt.Checked)

    def __advancedSettingsLinkActivate(self, link):
        self.__advancedSettingsShown = not self.__advancedSettingsShown
        self.__showHideAdvancedSettings()

    def __showHideAdvancedSettings(self):
        self.lbWebGIS.setVisible(not self.__advancedSettingsShown)
        self.leWebGIS.setVisible(not self.__advancedSettingsShown)
        self.lbName.setVisible(self.__advancedSettingsShown)
        self.leName.setVisible(self.__advancedSettingsShown)
        self.lbUrl.setVisible(self.__advancedSettingsShown)
        self.leUrl.setVisible(self.__advancedSettingsShown)

    @property
    def ngw_connection_settings(self):
        return self.ngw_conn_sett

    def accept(self):
        if not self.__advancedSettingsShown:
            url = "%s.nextgis.com" % self.leWebGIS.text()
            name = self.leWebGIS.text()
        else:
            url = self.leUrl.text()
            name = self.leName.text()

        if url[0:7] != "http://":
            url = "http://%s" % url

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
