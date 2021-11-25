# -*- coding: utf-8 -*-
"""
/***************************************************************************
 NGW Plugins settings

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
from .common_plugin_settings import PluginSettings
from ..core.ngw_connection_settings import NGWConnectionSettings


class NgwPluginSettings(PluginSettings):
    '''
    Settings class for working with ngw connection settings
    '''

    _company_name = 'NextGIS'
    _product = 'NextGIS WEB API'

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
            settings.value(key + '/server_url', '', type=str),
            settings.value(key + '/username', '', type=str),
            settings.value(key + '/password', '', type=str)
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
        return settings.value('/ui/selectedConnection', '', type=str)

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

    @classmethod
    def set_sanitize_rename_fields(cls, value):
        settings = cls.get_settings()
        settings.setValue('/sanitize_rename_fields', int(value))

    @classmethod
    def get_sanitize_rename_fields(cls):
        settings = cls.get_settings()
        option = settings.value('/sanitize_rename_fields', 1, type=int)
        return bool(option)

    @classmethod
    def set_sanitize_fix_geometry(cls, value):
        settings = cls.get_settings()
        settings.setValue('/sanitize_fix_geometry', int(value))

    @classmethod
    def get_sanitize_fix_geometry(cls):
        settings = cls.get_settings()
        option = settings.value('/sanitize_fix_geometry', 1, type=int)
        return bool(option)

    @classmethod
    def set_force_qgis_project_import(cls, value):
        settings = cls.get_settings()
        settings.setValue('/force_qgis_project_import', int(value))

    @classmethod
    def get_force_qgis_project_import(cls):
        settings = cls.get_settings()
        option = settings.value('/force_qgis_project_import', 1, type=int)
        return bool(option)

    @classmethod
    def set_upload_cog_rasters(cls, val):
        settings = cls.get_settings()
        settings.setValue('/upload_cog_rasters', val)

    @classmethod
    def get_upload_cog_rasters(cls):
        settings = cls.get_settings()
        return settings.value('/upload_cog_rasters', True, type=bool)


