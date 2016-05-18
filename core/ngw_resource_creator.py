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
import json
import requests
from .ngw_error import NGWError
from .ngw_resource import NGWResource
from .ngw_group_resource import NGWGroupResource
from .ngw_vector_layer import NGWVectorLayer
from .ngw_raster_layer import NGWRasterLayer
from .ngw_mapserver_style import NGWMapServerStyle
from .ngw_webmap import NGWWebMap


class ResourceCreator():

    @staticmethod
    def create_group(parent_ngw_resource, new_group_name):
        connection = parent_ngw_resource._res_factory.connection
        url = parent_ngw_resource.get_api_collection_url()

        params = dict(
            resource=dict(
                cls=NGWGroupResource.type_id,
                parent=dict(id=parent_ngw_resource.common.id),
                display_name=new_group_name)
        )

        try:
            result = connection.post(url, params=params)
            ngw_resource = NGWGroupResource(
                parent_ngw_resource._res_factory,
                NGWResource.receive_resource_obj(
                    connection,
                    result['id']
                )
            )
            return ngw_resource
        except requests.exceptions.RequestException, e:
            raise NGWError('Cannot create resource. Server response:\n%s' % e.message)

    @staticmethod
    def create_vector_layer(parent_ngw_resource, filename, layer_name):
        connection = parent_ngw_resource._res_factory.connection

        try:
            with open(filename, 'rb') as f:
                shape_file_desc = connection.put('/file_upload/upload', data=f)
                # print " shape_file_desc: ", shape_file_desc
        except requests.exceptions.RequestException, e:
            raise NGWError('Cannot create vector layer. Server response:\n%s' % e.message)

        url = parent_ngw_resource.get_api_collection_url()
        params = dict(
            resource=dict(
                cls=NGWVectorLayer.type_id,
                parent=dict(id=parent_ngw_resource.common.id),
                display_name=layer_name
            ),
            vector_layer=dict(
                srs=dict(id=3857),
                source=shape_file_desc
            )
        )

        try:
            result = connection.post(url, params=params)
            # print "add vector_layer resource result: ", result
            ngw_resource = NGWResource.receive_resource_obj(
                connection,
                result['id']
            )

            return NGWVectorLayer(parent_ngw_resource._res_factory, ngw_resource)
        except requests.exceptions.RequestException, e:
            raise NGWError('Cannot create vector layer. Server response:\n%s' % e.message)

    @staticmethod
    def create_vector_layer_style(ngw_vector_layer, style_filename, layer_name):
        connection = ngw_vector_layer._res_factory.connection
        style_name = layer_name + '-style'

        try:
            with open(style_filename, 'rb') as f:
                style_file_desc = connection.put('/file_upload/upload', data=f)
                # print " style_file_desc: ", style_file_desc
        except requests.exceptions.RequestException, e:
            raise NGWError('Cannot create style. Upload qml file. Server response:\n%s' % e.message)

        url = ngw_vector_layer.get_api_collection_url()
        params = dict(
            resource=dict(
                cls="qgis_vector_style",
                parent=dict(id=ngw_vector_layer.common.id),
                display_name=style_name
            ),
            qgis_vector_style=dict(
                file_upload=style_file_desc
            )
        )

        try:
            result = connection.post(url, params=params)
            # print "add qgis_vector_style resource result: ", result
            ngw_resource = NGWResource(
                ngw_vector_layer._res_factory,
                NGWResource.receive_resource_obj(
                    connection,
                    result['id']
                )
            )

            return ngw_resource
        except requests.exceptions.RequestException, e:
            raise NGWError('Cannot create vector layer style. Server response:\n%s' % e.message)

    @staticmethod
    def create_raster_layer(parent_ngw_resource, filename, layer_name):
        connection = parent_ngw_resource._res_factory.connection

        try:
            with open(filename, 'rb') as f:
                raster_file_desc = connection.put('/file_upload/upload', data=f)

        except requests.exceptions.RequestException, e:
            raise NGWError('Cannot create raster layer. Server response:\n%s' % e.message)

        url = parent_ngw_resource.get_api_collection_url()
        params = dict(
            resource=dict(
                cls=NGWRasterLayer.type_id,
                parent=dict(id=parent_ngw_resource.common.id),
                display_name=layer_name
            ),
            raster_layer=dict(
                srs=dict(id=3857),
                source=raster_file_desc
            )
        )

        try:
            result = connection.post(url, params=params)
            # print "add vector_layer resource result: ", result
            ngw_resource = NGWResource.receive_resource_obj(
                connection,
                result['id']
            )

            return NGWRasterLayer(parent_ngw_resource._res_factory, ngw_resource)
        except requests.exceptions.RequestException, e:
            raise NGWError('Cannot create raster layer. Server response:\n%s' % e.message)

    @staticmethod
    def create_raster_layer_style(ngw_raster_layer, layer_name):
        connection = ngw_raster_layer._res_factory.connection
        style_name = layer_name + '-style'

        url = ngw_raster_layer.get_api_collection_url()
        params = dict(
            resource=dict(
                cls="raster_style",
                parent=dict(id=ngw_raster_layer.common.id),
                display_name=style_name
            ),
        )

        try:
            result = connection.post(url, params=params)
            # print "add qgis_vector_style resource result: ", result
            ngw_resource = NGWResource(
                ngw_raster_layer._res_factory,
                NGWResource.receive_resource_obj(
                    connection,
                    result['id']
                )
            )

            return ngw_resource
        except requests.exceptions.RequestException, e:
            raise NGWError('Cannot create raster layer style. Server response:\n%s' % e.message)

    @staticmethod
    def create_webmap(parent_ngw_resource, ngw_webmap_name, ngw_webmap_items, bbox=[-180, 180, 90, -90]):
        connection = parent_ngw_resource._res_factory.connection
        url = parent_ngw_resource.get_api_collection_url()

        params = dict(
            resource=dict(
                cls=NGWWebMap.type_id,
                display_name=ngw_webmap_name,
                parent=dict(
                    id=parent_ngw_resource.common.id
                )
            ),
            webmap=dict(
                extent_left=bbox[0],
                extent_right=bbox[1],
                extent_top=bbox[2],
                extent_bottom=bbox[3],
                root_item=dict(
                    item_type="root",
                    children=ngw_webmap_items
                )
            )
        )

        # print "url: ", url
        # print "params: ", params

        try:
            result = connection.post(url, params=params)
            # print "add webmap resource result: ", result
            ngw_resource = NGWResource(
                parent_ngw_resource._res_factory,
                NGWResource.receive_resource_obj(
                    connection,
                    result['id']
                )
            )

            return ngw_resource
        except requests.exceptions.RequestException, e:
            raise NGWError('Cannot create webmap. Server response:\n%s' % e.message)
