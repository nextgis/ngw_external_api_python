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
from .ngw_resource import NGWResource
from .ngw_group_resource import NGWGroupResource
from .ngw_vector_layer import NGWVectorLayer
from .ngw_raster_layer import NGWRasterLayer
from .ngw_wfs_service import NGWWfsService
from .ngw_webmap import NGWWebMap

from ..qgis.compat_qgis import CompatQgis


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

        result = connection.post(url, params=params)

        ngw_resource = NGWGroupResource(
            parent_ngw_resource._res_factory,
            NGWResource.receive_resource_obj(
                connection,
                result['id']
            )
        )
        return ngw_resource

    @staticmethod
    def create_vector_layer(parent_ngw_resource, filename, layer_name, callback,
        geom_type=None, geom_is_multi=None, geom_haz_z=None):
        connection = parent_ngw_resource._res_factory.connection

        shape_file_desc = connection.upload_file(filename, callback)

        url = parent_ngw_resource.get_api_collection_url()
        params = dict(
            resource=dict(
                cls=NGWVectorLayer.type_id,
                parent=dict(id=parent_ngw_resource.common.id),
                display_name=layer_name
            ),
            vector_layer=dict(
                srs=dict(id=3857),
                source=shape_file_desc,

                # Should force geometry type in case of 0 features: NGW defines geom type by first feature.
                # Force only for QGIS >= 3 because QGIS 2 defines geometry type of Shapefile incorrectly.
                # TODO: check that for NGW < 3.8.0 it is ok to pass these parameters.
                cast_geometry_type=geom_type if not CompatQgis.is_qgis_2() else None,
                cast_is_multi=geom_is_multi if not CompatQgis.is_qgis_2() else None,
                cast_haz_z=geom_haz_z if not CompatQgis.is_qgis_2() else None,
                fix_errors='LOSSY',
                skip_errors=True
            )
        )

        result = connection.post(url, params=params)
        ngw_resource = NGWResource.receive_resource_obj(
            connection,
            result['id']
        )

        return NGWVectorLayer(parent_ngw_resource._res_factory, ngw_resource)

    @staticmethod
    def create_raster_layer(parent_ngw_resource, filename, layer_name, callback):
        connection = parent_ngw_resource._res_factory.connection

        raster_file_desc = connection.upload_file(filename, callback)

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

        result = connection.post(url, params=params)
        # print "add vector_layer resource result: ", result
        ngw_resource = NGWResource.receive_resource_obj(
            connection,
            result['id']
        )

        return NGWRasterLayer(parent_ngw_resource._res_factory, ngw_resource)

    @staticmethod
    def create_wfs_service(name, ngw_group_resource, ngw_layers, ret_obj_num):
        connection = ngw_group_resource._res_factory.connection
        url = ngw_group_resource.get_api_collection_url()

        params_layers = []
        for ngw_layer in ngw_layers:
            params_layer = dict(
                display_name=ngw_layer.common.display_name,
                keyname="ngw_id_%d" % ngw_layer.common.id,
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

        result = connection.post(url, params=params)

        ngw_resource = NGWWfsService(
            ngw_group_resource._res_factory,
            NGWResource.receive_resource_obj(
                connection,
                result['id']
            )
        )

        return ngw_resource
