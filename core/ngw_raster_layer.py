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
from ngw_resource import NGWResource, API_LAYER_EXTENT

from ..utils import ICONS_DIR


class NGWRasterLayer(NGWResource):

    type_id = 'raster_layer'
    icon_path = path.join(ICONS_DIR, 'raster_layer.svg')
    type_title = 'NGW Raster Layer'

    def __init__(self, resource_factory, resource_json):
        NGWResource.__init__(self, resource_factory, resource_json)

    def extent(self):
        result = self._res_factory.connection.get(
            API_LAYER_EXTENT(self.common.id)
        )
        extent = result.get('extent')
        if extent is None:
            return (-180, 180, -90, 90)

        return (
            extent.get('minLon', -180),
            extent.get('maxLon', 180),
            extent.get('minLat', -90),
            extent.get('maxLat', 90),
        )

    def create_style(self):
        """Create default style for this layer
        """
        connection = self._res_factory.connection
        style_name = self.generate_unique_child_name(
            self.common.display_name + '-style'
        )

        params = dict(
            resource=dict(
                cls="raster_style",
                parent=dict(id=self.common.id),
                display_name=style_name
            ),
        )

        url = self.get_api_collection_url()
        result = connection.post(url, params=params)
        ngw_resource = NGWResource(
            self._res_factory,
            NGWResource.receive_resource_obj(
                connection,
                result['id']
            )
        )

        return ngw_resource
