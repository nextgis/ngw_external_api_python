# -*- coding: utf-8 -*-
"""
/***************************************************************************
    NextGIS WEB API
                              -------------------
        begin                : 2016-06-02
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
from .ngw_resource import NGWResource

from ..utils import ICONS_DIR


class NGWQGISStyle(NGWResource):
    icon_path = path.join(ICONS_DIR, 'style.png')

    def __init__(self, resource_factory, resource_json):
        NGWResource.__init__(self, resource_factory, resource_json)

    def download_qml_url(self):
        return self.get_absolute_api_url() + "/qml"

    def update_qml(self, qml, callback):
        connection = self._res_factory.connection

        style_file_desc = connection.upload_file(qml, callback)

        params = dict(
            resource=dict(
                display_name=self.common.display_name,

            ),
        )
        params[self.type_id] = dict(
            file_upload=style_file_desc
        )

        url = self.get_relative_api_url()
        connection.put(url, params=params)
        self.update()

    def get_creds_for_qml(self):
        creds = self._res_factory.connection.get_auth()
        if creds is None or len(creds) != 2:
            return None
        if creds[0] is None or creds[0] == '':
            return None
        return creds[0], creds[1] # do not quot this because it is used as header when downloading qml style


class NGWQGISVectorStyle(NGWQGISStyle):
    type_id = 'qgis_vector_style'
    type_title = 'NGW QGIS Vector Style'

    def __init__(self, resource_factory, resource_json):
        NGWQGISStyle.__init__(self, resource_factory, resource_json)


class NGWQGISRasterStyle(NGWQGISStyle):
    type_id = 'qgis_raster_style'
    type_title = 'NGW QGIS Raster Style'

    def __init__(self, resource_factory, resource_json):
        NGWQGISStyle.__init__(self, resource_factory, resource_json)



