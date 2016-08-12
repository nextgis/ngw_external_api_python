# -*- coding: utf-8 -*-
"""
/***************************************************************************
    NextGIS WEB API
                              -------------------
        begin                : 2014-11-19
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


class NGWConnectionSettings():
    def __init__(self, connection_name=None, server_url=None, username=None, password=None):
        self.connection_name = connection_name
        self.server_url = server_url
        self.username = username
        self.password = password

    def __eq__(self, connection_settings):
        if connection_settings is None:
            return False

        if self.server_url != connection_settings.server_url:
            return False

        if self.username != connection_settings.username:
            return False

        if self.password != connection_settings.password:
            return False

        return True
