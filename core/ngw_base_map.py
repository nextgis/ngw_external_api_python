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

from os import path
from .ngw_resource import NGWResource, DICT_TO_OBJ, LIST_DICT_TO_LIST_OBJ

from ..utils import ICONS_DIR, log


class NGWBaseMap(NGWResource):

    type_id = 'basemap_layer'
    icon_path = path.join(ICONS_DIR, 'base_map.svg')
    type_title = 'NGW Base Map layer'

    def __init__(self, resource_factory, resource_json):
        NGWResource.__init__(self, resource_factory, resource_json)

    @classmethod
    def create_in_group(cls, name, ngw_group_resource, base_map_url, qms_ext_settings=None):
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

        qms_parameters = None
        if qms_ext_settings is not None:
            qms_parameters = qms_ext_settings.toJSON()

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


class NGWBaseMapExtSettings(object):
    """docstring for NGWBaseMapExtSettings"""
    def __init__(self, url, epsg, z_min, z_max, y_origin_top):
        super(NGWBaseMapExtSettings, self).__init__()
        self.url = url
        self.epsg = int(epsg)
        self.z_min = z_min
        self.z_max = z_max
        self.y_origin_top = y_origin_top
    
    def toJSON(self):
        d = {}
        if self.url is None:
            return None
        d["url"] = self.url
        if self.epsg is None:
            return None
        d["epsg"] = self.epsg
        if self.z_min is not None:
            d["z_min"] = self.z_min
        if self.z_max is not None:
            d["z_max"] = self.z_max
        if self.y_origin_top is not None:
            d["y_origin_top"] = self.y_origin_top

        return json.dumps(d)