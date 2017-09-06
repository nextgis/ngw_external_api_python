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
from ngw_resource import NGWResource, DICT_TO_OBJ, LIST_DICT_TO_LIST_OBJ

from ..utils import ICONS_DIR, log


class NGWBaseMap(NGWResource):

    type_id = 'basemap_layer'
    icon_path = path.join(ICONS_DIR, 'base_map.svg')
    type_title = 'NGW Base Map layer'

    def __init__(self, resource_factory, resource_json):
        NGWResource.__init__(self, resource_factory, resource_json)

    @classmethod
    def create_in_group(cls, name, ngw_group_resource, base_map_url, qms_parameters=None):
        connection = ngw_group_resource._res_factory.connection
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
            url=base_map_url,
            qms=qms_parameters
        )
        result = connection.post(ngw_group_resource.get_api_collection_url(), params=params)

        ngw_resource = cls(
            ngw_group_resource._res_factory,
            NGWResource.receive_resource_obj(
                connection,
                result['id']
            )
        )

        return ngw_resource

