# -*- coding: utf-8 -*-
"""
/***************************************************************************
 Plugins settings
                                 A QGIS plugin
 Compulink QGIS tools
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
from PyQt4.QtCore import QSettings
from ..core.ngw_connection_settings import NGWConnectionSettings


class PluginSettings():

    _company_name = 'AnyCompany'
    _product = 'AnyPlugin'

    @classmethod
    def get_settings(cls):
        return QSettings(cls._company_name, cls._product)

    @classmethod
    def remove_ngw_connection(cls, connection_name):
        settings = cls.get_settings()
        key = '/connections/' + connection_name
        settings.remove(key)

    @classmethod
    def get_ngw_connection(cls, connection_name):
        settings = cls.get_settings()
        key = '/connections/' + connection_name

        return NGWConnectionSettings(
            connection_name,
            settings.value(key + '/server_url', ''),
            settings.value(key + '/username', ''),
            settings.value(key + '/password', '')
        )

    @classmethod
    def save_ngw_connection(cls, connection_settings):
        settings = cls.get_settings()
        key = '/connections/' + connection_settings.connection_name
        settings.setValue(key + '/server_url', connection_settings.server_url)
        settings.setValue(key + '/username', connection_settings.username)
        settings.setValue(key + '/password', connection_settings.password)

    @classmethod
    def get_selected_ngw_connection_name(cls):
        settings = cls.get_settings()
        return settings.value('/ui/selectedConnection', '')

    @classmethod
    def set_selected_ngw_connection_name(cls, connection_name):
        settings = cls.get_settings()
        settings.setValue('/ui/selectedConnection', connection_name)

    @classmethod
    def get_ngw_connection_names(cls):
        settings = cls.get_settings()
        settings.beginGroup('/connections')
        connections = settings.childGroups()
        settings.endGroup()
        return connections