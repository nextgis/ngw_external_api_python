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
from typing import Tuple, Optional

from qgis.core import QgsDataSourceUri

from .ngw_resource import NGWResource, DICT_TO_OBJ, LIST_DICT_TO_LIST_OBJ


class NGWWfsService(NGWResource):

    type_id = 'wfsserver_service'

    def _construct(self):
        super()._construct()
        # wfsserver_service
        self.wfs = DICT_TO_OBJ(self._json[self.type_id])
        if hasattr(self.wfs, "layers"):
            self.wfs.layers = LIST_DICT_TO_LIST_OBJ(self.wfs.layers)

    def get_wfs_url(self, layer_keyname):
        uri = QgsDataSourceUri()
        creds = self.get_creds_for_url()
        if creds[0] and creds[1]:
            uri.setUsername(creds[0])
            uri.setPassword(creds[1])
        uri.setParam('typename', layer_keyname)
        uri.setParam('srsname', 'EPSG:3857')
        uri.setParam('version', 'auto')
        uri.setParam('url', self.get_absolute_api_url() + '/wfs')
        uri.setParam('restrictToRequestBBOX', '1')

        return uri.uri(True)

    def get_creds_for_url(self) -> Tuple[Optional[str], Optional[str]]:
        creds = self.get_creds()
        if not creds[0] or not creds[1]:
            return creds

        # It seems we should escape only '&' character, but not other reserved
        # ones in a password. The use of urllib.parse.quote_plus() on a
        # password leads to WFS authentication errors when other symbols occur
        # such as '.', '+', '@'. Understand why. What else and how should we
        # correcyly replace here? Also this approach does not work in QGIS 2.
        login = creds[0]
        password = creds[1].replace('&', '%26')
        return login, password

    def get_layers(self):
        return self._json["wfsserver_service"]["layers"]

    def get_source_layer(self, layer_id):
        return self._res_factory.get_resource(layer_id)
