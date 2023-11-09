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

from .ngw_resource import NGWResource, API_LAYER_EXTENT
from .ngw_qgis_style import NGWQGISRasterStyle

from ..utils import ICONS_DIR


class NGWRasterLayer(NGWResource):

    type_id = 'raster_layer'
    type_title = 'NGW Raster Layer'

    def __init__(self, resource_factory, resource_json):
        super().__init__(resource_factory, resource_json)
        self.is_cog = resource_json['raster_layer'].get('cog', False)

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
            self.common.display_name + ''
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

    def create_qml_style(self, qml, callback, style_name=None) -> NGWQGISRasterStyle:
        """Create QML style for this layer

        qml - full path to qml file
        callback - upload file callback
        """
        connection = self._res_factory.connection
        if not style_name:
            style_name = self.generate_unique_child_name(
                self.common.display_name + ''
            )

        style_file_desc = connection.upload_file(qml, callback)

        params = dict(
            resource=dict(
                cls=NGWQGISRasterStyle.type_id,
                parent=dict(id=self.common.id),
                display_name=style_name
            ),
        )
        params[NGWQGISRasterStyle.type_id] = dict(
            file_upload=style_file_desc
        )

        url = self.get_api_collection_url()
        result = connection.post(url, params=params)
        ngw_resource = NGWQGISRasterStyle(
            self._res_factory,
            NGWResource.receive_resource_obj(
                connection,
                result['id']
            )
        )

        return ngw_resource
