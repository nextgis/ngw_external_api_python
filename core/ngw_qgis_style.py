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

from typing import Optional, Tuple

from ..utils import ICONS_DIR


class NGWQGISStyle(NGWResource):
    icon_path = path.join(ICONS_DIR, 'style.png')

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

    def get_creds_for_qml(self) -> Tuple[Optional[str], Optional[str]]:
        # do not quot this because it is used as header when downloading
        # qml style
        return self.get_creds()


class NGWQGISVectorStyle(NGWQGISStyle):
    type_id = 'qgis_vector_style'
    type_title = 'NGW QGIS Vector Style'


class NGWQGISRasterStyle(NGWQGISStyle):
    type_id = 'qgis_raster_style'
    type_title = 'NGW QGIS Raster Style'
