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

from ..utils import ICONS_DIR


class NGWWebMap(NGWResource):

    type_id = 'webmap'
    icon_path = path.join(ICONS_DIR, 'web_map.svg')
    type_title = 'NGW Web Map'

    def __init__(self, resource_factory, resource_json):
        NGWResource.__init__(self, resource_factory, resource_json)

    def get_display_url(self):
        return '%s/%s' % (
            self.get_absolute_url(),
            'display'
        )

    @classmethod
    def create_in_group(cls, name, ngw_group_resource, ngw_webmap_items, ngw_base_maps=[], bbox=[-180, 180, 90, -90]):
        connection = ngw_group_resource._res_factory.connection
        url = ngw_group_resource.get_api_collection_url()

        base_maps = []
        for ngw_base_map in ngw_base_maps:
            base_maps.append(
                {
                    "display_name": ngw_base_map.common.display_name,
                    "resource_id": ngw_base_map.common.id,
                    "enabled": True,
                    "opacity": None,
                }
            )
        web_map_base_maps = dict(
            basemaps=base_maps,
        )

        web_map = dict(
            extent_left=bbox[0],
            extent_right=bbox[1],
            extent_top=bbox[2],
            extent_bottom=bbox[3],
            root_item=dict(
                item_type="root",
                children=ngw_webmap_items
            )
        )

        params = dict(
            resource=dict(
                cls=NGWWebMap.type_id,
                display_name=name,
                parent=dict(
                    id=ngw_group_resource.common.id
                )
            ),
            webmap=web_map,
            basemap_webmap=web_map_base_maps,
        )

        result = connection.post(url, params=params)

        ngw_resource = NGWWebMap(
            ngw_group_resource._res_factory,
            NGWResource.receive_resource_obj(
                connection,
                result['id']
            )
        )

        return ngw_resource


class NGWWebMapItem(object):
    ITEM_TYPE_ROOT = "root"
    ITEM_TYPE_LAYER = "layer"
    ITEM_TYPE_GROUP = "group"

    def __init__(self, item_type):
        self.item_type = item_type
        self.children = []

    def appendChild(self, ngw_web_map_item):
        self.children.append(ngw_web_map_item)

    def toDict(self):
        struct = dict(
            item_type=self.item_type,
            children=[]
        )
        struct.update(self._attributes())

        for child in self.children:
            struct["children"].append(
                child.toDict()
            )

        return struct

    def _attributes(self):
        return NotImplementedError


class NGWWebMapRoot(NGWWebMapItem):
    def __init__(self):
        NGWWebMapItem.__init__(self, NGWWebMapItem.ITEM_TYPE_ROOT)

    def __attributes(self):
        return dict()


class NGWWebMapLayer(NGWWebMapItem):
    def __init__(self, layer_style_id, display_name, is_visible, transparency):
        NGWWebMapItem.__init__(self, NGWWebMapItem.ITEM_TYPE_LAYER)
        self.layer_style_id = layer_style_id
        self.display_name = display_name
        self.is_visible = is_visible
        self.transparency = transparency

    def _attributes(self):
        return dict(
            layer_style_id=self.layer_style_id,
            display_name=self.display_name,
            layer_adapter="image",
            layer_enabled=self.is_visible,
            layer_max_scale_denom=None,
            layer_min_scale_denom=None,
            layer_transparency=self.transparency
        )


class NGWWebMapGroup(NGWWebMapItem):
    def __init__(self, display_name, expanded=True):
        NGWWebMapItem.__init__(self, NGWWebMapItem.ITEM_TYPE_GROUP)
        self.display_name = display_name
        self.expanded = expanded

    def _attributes(self):
        return dict(
            display_name=self.display_name,
            group_expanded=self.expanded,
        )
