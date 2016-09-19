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
import os
import requests
from .ngw_error import NGWError
from .ngw_resource import NGWResource
from .ngw_group_resource import NGWGroupResource
from .ngw_vector_layer import NGWVectorLayer
from .ngw_raster_layer import NGWRasterLayer
from .ngw_wfs_service import NGWWfsService
from .ngw_webmap import NGWWebMap


class File2Upload(file):
    def __init__(self, path, callback):
        file.__init__(self, path, "rb")
        self.seek(0, os.SEEK_END)
        self._total = self.tell()
        self._readed = 0
        self.seek(0)
        self._callback = callback

    def __len__(self):
        return self._total

    def read(self, size):
        data = file.read(self, size)
        self._readed += len(data)
        self._callback(self._total, self._readed)
        return data


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
    def create_vector_layer(parent_ngw_resource, filename, layer_name, callback):
        connection = parent_ngw_resource._res_factory.connection

        try:
            with File2Upload(filename, callback) as f:
                shape_file_desc = connection.put('/file_upload/upload', data=f)

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
            ngw_resource = NGWResource.receive_resource_obj(
                connection,
                result['id']
            )

            return NGWVectorLayer(parent_ngw_resource._res_factory, ngw_resource)
        except requests.exceptions.RequestException, e:
            raise NGWError('Cannot create vector layer. Server response:\n%s' % e.message)

    @staticmethod
    def create_raster_layer(parent_ngw_resource, filename, layer_name, callback):
        connection = parent_ngw_resource._res_factory.connection

        try:
            with File2Upload(filename, callback) as f:
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

        try:
            result = connection.post(url, params=params)
            # print "add webmap resource result: ", result
            ngw_resource = NGWWebMap(
                parent_ngw_resource._res_factory,
                NGWResource.receive_resource_obj(
                    connection,
                    result['id']
                )
            )

            return ngw_resource
        except requests.exceptions.RequestException, e:
            raise NGWError('Cannot create webmap. Server response:\n%s' % e.message)

    @staticmethod
    def create_wfs_service(name, ngw_group_resource, ngw_layers, ret_obj_num):
        connection = ngw_group_resource._res_factory.connection
        url = ngw_group_resource.get_api_collection_url()

        params_layers = []
        for ngw_layer in ngw_layers:
            ngw_layer_name = ngw_layer.common.display_name
            params_layer = dict(
                display_name=ngw_layer_name,
                keyname=ngw_layer_name.lower().replace(' ', '_'),
                resource_id=ngw_layer.common.id,
                maxfeatures=ret_obj_num
            )
            params_layers.append(params_layer)

        params = dict(
            resource=dict(
                cls=NGWWfsService.type_id,
                display_name=name,
                parent=dict(
                    id=ngw_group_resource.common.id
                )
            ),
            wfsserver_service=dict(
                layers=params_layers
            )
        )

        try:
            result = connection.post(url, params=params)

            ngw_resource = NGWWfsService(
                ngw_group_resource._res_factory,
                NGWResource.receive_resource_obj(
                    connection,
                    result['id']
                )
            )

            return ngw_resource
        except requests.exceptions.RequestException, e:
            raise NGWError('Cannot create wfs service. Server response:\n%s' % e.message)
