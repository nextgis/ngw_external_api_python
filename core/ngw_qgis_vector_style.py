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
import requests
from ngw_resource import NGWResource

from ..utils import ICONS_DIR


class NGWQGISVectorStyle(NGWResource):

    type_id = 'qgis_vector_style'
    icon_path = path.join(ICONS_DIR, 'style.png')
    type_title = 'NGW QGIS Vector Style'

    def __init__(self, resource_factory, resource_json):
        NGWResource.__init__(self, resource_factory, resource_json)

    def download_qml_url(self):
        return self.get_absolute_api_url() + "/qml"

    def update_qml(self, qml, callback):
        """Create QML style for this layer

        qml - full path to qml file
        callback - upload file callback, pass to File2Upload (ngw_resource.py)
        """
        connection = self._res_factory.connection

        try:
            style_file_desc = connection.upload_file(filename, callback)
        except requests.exceptions.RequestException, e:
            raise NGWError('Cannot create style. Upload qml file. Server response:\n%s' % e.message)

        params = dict(
            resource=dict(
                display_name=self.common.display_name,

            ),
        )
        params[self.type_id] = dict(
            file_upload=style_file_desc
        )

        try:
            url = self.get_relative_api_url()
            connection.put(url, params=params)
            self.update()
        except requests.exceptions.RequestException, e:
            raise NGWError('Cannot create vector layer style. Server response:\n%s' % e.message)