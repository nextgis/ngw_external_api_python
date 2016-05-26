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
from PyQt4 import uic
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
        self.setFixedSize(self.size())

        self.ngw_conn_sett = ngw_connection_settings

        if self.ngw_conn_sett is not None:
            self.leName.setText(self.ngw_conn_sett.connection_name)
            self.leUrl.setText(self.ngw_conn_sett.server_url)
            self.leUser.setText(self.ngw_conn_sett.username)
            self.lePassword.setText(self.ngw_conn_sett.password)

    @property
    def ngw_connection_settings(self):
        return self.ngw_conn_sett

    def accept(self):
        url = self.leUrl.text()
        if url[0:7] != "http://":
           url = "http://%s" % url 
        self.ngw_conn_sett = NGWConnectionSettings(
            self.leName.text(),
            url,
            self.leUser.text(),
            self.lePassword.text())

        QDialog.accept(self)
