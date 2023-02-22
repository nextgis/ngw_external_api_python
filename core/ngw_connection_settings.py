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


class NGWConnectionSettings:
    def __init__(self, connection_name=None, server_url=None, username=None, password=None):
        self.connection_name = connection_name
        self.server_url = server_url
        self.username = username
        self.password = password

        self.proxy_enable = False

    def set_proxy(self, host, port, user, password):
        self.proxy_enable = True
        self.proxy_host = host
        self.proxy_port = port
        self.proxy_user = user
        self.proxy_password = password

    def __eq__(self, other):
        if other is None:
            return False
        if self.server_url != other.server_url:
            return False
        if self.username != other.username:
            return False
        if self.password != other.password:
            return False
        return True

    def equalWoProtocol(self, other):
        if other is None:
            return False
        url1 = self.server_url.replace('https://', '').replace('http://', '')
        url2 = other.server_url.replace('https://', '').replace('http://', '')
        if url1 != url2:
            return False
        if self.username != other.username:
            return False
        if self.password != other.password:
            return False
        return True
