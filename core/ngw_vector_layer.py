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
from ngw_resource import NGWResource


class NGWVectorLayer(NGWResource):

    type_id = 'vector_layer'
    icon_path = path.join(path.dirname(__file__), path.pardir, 'icons/', 'vector_layer.svg')
    type_title = 'NGW Vector Layer'

    icons = {
        "POINT": "vector_layer_point.svg",
        "MULTIPOINT": "vector_layer_mpoint.svg",
        "LINESTRING": "vector_layer_line.svg",
        "MULTILINESTRING": "vector_layer_mline.svg",
        "POLYGON": "vector_layer_polygon.svg",
        "MULTIPOLYGON": "vector_layer_mpolygon.svg",
    }

    def __init__(self, resource_factory, resource_json):
        NGWResource.__init__(self, resource_factory, resource_json)

        if self.type_id in self._json:
            if "geometry_type" in self._json[self.type_id]:
                self.set_icon(self._json[self.type_id]["geometry_type"])

    def get_geojson_url(self):
        return '%s/%s/' % (
            self.get_absolute_url_with_auth(),
            'geojson'
        )

    def set_icon(self, geometry_type):
        icon_filename = self.icons.get(geometry_type, 'vector_layer.svg')
        self.icon_path = path.join(path.dirname(__file__), path.pardir, 'icons/', icon_filename)
