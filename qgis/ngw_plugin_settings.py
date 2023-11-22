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


class NgwPluginSettings(PluginSettings):
    '''
    Settings class for working with ngw connection settings
    '''

    _company_name = 'NextGIS'
    _product = 'NextGIS WEB API'

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
    def set_upload_cog_rasters(cls, val):
        settings = cls.get_settings()
        settings.setValue('/upload_cog_rasters', val)

    @classmethod
    def get_upload_cog_rasters(cls):
        settings = cls.get_settings()
        return settings.value('/upload_cog_rasters', True, type=bool)
