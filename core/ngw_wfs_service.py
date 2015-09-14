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
from ngw_resource import NGWResource, DICT_TO_OBJ, LIST_DICT_TO_LIST_OBJ


class NGWWfsService(NGWResource):

    type_id = 'wfsserver_service'
    icon_path = path.join(path.dirname(__file__), path.pardir, 'icons/', 'wfs.svg')
    type_title = 'NGW WFS Service'

    def _construct(self):
        NGWResource._construct(self)
        #wfsserver_service
        self.wfs = DICT_TO_OBJ(self._json['wfsserver_service'])
        if self.wfs.layers:
            self.wfs.layers = LIST_DICT_TO_LIST_OBJ(self.wfs.layers)

    def get_wfs_url(self, layer_keyname):
        return '%s%s%s' % (
            self.get_absolute_api_url(),
            '/wfs?SERVICE=WFS&TYPENAME=%s' % layer_keyname,
            '&username=%s&password=%s' % self._res_factory.connection.get_auth()
        )
    
    def get_layers(self):
        return self._json["wfsserver_service"]["layers"]