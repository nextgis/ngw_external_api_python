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
from .ngw_resource import NGWResource

from ..utils import ICONS_DIR


class NGWWmsLayer(NGWResource):

    type_id = 'wmsclient_layer'
    type_title = 'NGW WMS Layer'

    def _construct(self):
        super()._construct()
        self.ngw_wms_connection_url = None
        self.ngw_wms_layers = []

        wms_layer_desc = self._json.get(self.type_id, {})
        wms_connection_id = wms_layer_desc.get("connection", {}).get("id")
        if wms_connection_id is not None:
            wms_connection = self._res_factory.get_resource(wms_connection_id)
            self.ngw_wms_connection_url = wms_connection.get_connection_url()
        self.ngw_wms_layers = wms_layer_desc.get("wmslayers").split(",")

    @classmethod
    def create_in_group(cls, name, ngw_group_resource, ngw_wms_connection_id, wms_layers, wms_format):
        connection = ngw_group_resource._res_factory.connection
        url = ngw_group_resource.get_api_collection_url()

        params = dict(
            resource=dict(
                cls=cls.type_id,
                display_name=name,
                parent=dict(
                    id=ngw_group_resource.common.id
                )
            )
        )

        params[cls.type_id] = dict(
            connection=dict(
                id=ngw_wms_connection_id
            ),
            wmslayers=",".join(wms_layers),
            imgformat=wms_format,
            srs=dict(
                id=3857
            ),
        )

        result = connection.post(url, params=params)

        ngw_resource = cls(
            ngw_group_resource._res_factory,
            NGWResource.receive_resource_obj(
                connection,
                result['id']
            )
        )

        return ngw_resource
