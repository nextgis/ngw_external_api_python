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
from ngw_resource import NGWResource


class NGWQGISVectorStyle(NGWResource):

    type_id = 'qgis_vector_style'
    icon_path = path.join(path.dirname(__file__), path.pardir, 'icons/', 'style.png')
    type_title = 'NGW QGIS Vector Style'

    def __init__(self, resource_factory, resource_json):
        NGWResource.__init__(self, resource_factory, resource_json)

        self.common.display_name = "(qgis) " + self.common.display_name

    def download_qml_url(self):
        return self.get_absolute_api_url() + "/qml"
