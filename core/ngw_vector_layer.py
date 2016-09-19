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
import requests
from os import path
from ngw_resource import NGWResource, API_LAYER_EXTENT, File2Upload
from ngw_qgis_vector_style import NGWQGISVectorStyle
from ngw_mapserver_style import NGWMapServerStyle
from ngw_error import NGWError


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

    def create_qml_style(self, qml, callback):
        """Create QML style for this layer

        qml - full path to qml file
        callback - upload file callback, pass to File2Upload
        """
        connection = self._res_factory.connection
        style_name = self.generate_unique_child_name(
            self.common.display_name + '-style'
        )

        try:
            with File2Upload(qml, callback) as f:
                style_file_desc = connection.put('/file_upload/upload', data=f)
        except requests.exceptions.RequestException, e:
            raise NGWError('Cannot create style. Upload qml file. Server response:\n%s' % e.message)

        params = dict(
            resource=dict(
                cls=NGWQGISVectorStyle.type_id,
                parent=dict(id=self.common.id),
                display_name=style_name
            ),
        )
        params[NGWQGISVectorStyle.type_id] = dict(
            file_upload=style_file_desc
        )

        try:
            url = self.get_api_collection_url()
            result = connection.post(url, params=params)
            ngw_resource = NGWQGISVectorStyle(
                self._res_factory,
                NGWResource.receive_resource_obj(
                    connection,
                    result['id']
                )
            )

            return ngw_resource
        except requests.exceptions.RequestException, e:
            raise NGWError('Cannot create vector layer style. Server response:\n%s' % e.message)

    def create_map_server_style(self):
        """Create default Map Srver style for this layer
        """
        connection = self._res_factory.connection

        style_name = self.generate_unique_child_name(
            self.common.display_name + '-style'
        )

        params = dict(
            resource=dict(
                cls=NGWMapServerStyle.type_id,
                parent=dict(id=self.common.id),
                display_name=style_name
            ),
        )

        try:
            url = self.get_api_collection_url()
            result = connection.post(url, params=params)
            ngw_resource = NGWMapServerStyle(
                self._res_factory,
                NGWResource.receive_resource_obj(
                    connection,
                    result['id']
                )
            )

            return ngw_resource
        except requests.exceptions.RequestException, e:
            raise NGWError('Cannot create vector layer style. Server response:\n%s' % e.message)