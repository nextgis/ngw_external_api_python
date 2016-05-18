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


class NGWRasterLayer(NGWResource):

    type_id = 'raster_layer'
    icon_path = path.join(path.dirname(__file__), path.pardir, 'icons/', 'raster_layer.svg')
    type_title = 'NGW Raster Layer'

    def __init__(self, resource_factory, resource_json):
        NGWResource.__init__(self, resource_factory, resource_json)

    def get_geojson_url(self):
        return '%s/%s/' % (
            self.get_absolute_url_with_auth(),
            'geojson'
        )
