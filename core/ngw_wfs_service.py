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
from os import path
import urllib.parse

from .ngw_resource import NGWResource, DICT_TO_OBJ, LIST_DICT_TO_LIST_OBJ

from ..utils import ICONS_DIR, log


class NGWWfsService(NGWResource):

    type_id = 'wfsserver_service'
    icon_path = path.join(ICONS_DIR, 'wfs.svg')
    type_title = 'NGW WFS Service'

    def __init__(self, resource_factory, resource_json):
        NGWResource.__init__(self, resource_factory, resource_json)

    def _construct(self):
        NGWResource._construct(self)
        #wfsserver_service
        self.wfs = DICT_TO_OBJ(self._json[self.type_id])
        if hasattr(self.wfs, "layers"):
            self.wfs.layers = LIST_DICT_TO_LIST_OBJ(self.wfs.layers)

    def get_wfs_url(self, layer_keyname):
        creds = self.get_creds_for_url()
        creds_str = ''
        if creds is not None:
            creds_str = '&username=%s&password=%s' % (creds[0], creds[1])
        return '%s%s%s' % (
            self.get_absolute_api_url(),
            '/wfs?SERVICE=WFS&TYPENAME=%s' % layer_keyname,
            creds_str
        )

    def get_creds_for_url(self):
        creds = self.get_creds()
        if creds is None or creds[0] == '' or creds[1] == '':
            return None
        # It seems we should escape only '&' character, but not other reserved ones in a password. The use of
        # urllib.parse.quote_plus() on a password leads to WFS authentication errors when other symbols occur
        # such as '.', '+', '@'. Understand why. What else and how should we correcyly replace here?
        # Also this approach does not work in QGIS 2.
        login = creds[0]
        password = creds[1].replace('&', '%26')
        return login, password


    def get_layers(self):
        return self._json["wfsserver_service"]["layers"]

    def get_source_layer(self, layer_id):
        return self._res_factory.get_resource(layer_id)