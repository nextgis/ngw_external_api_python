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
from ngw_resource import NGWResource, API_LAYER_EXTENT
from ngw_qgis_vector_style import NGWQGISVectorStyle
from ngw_mapserver_style import NGWMapServerStyle
from ngw_error import NGWError
from ngw_feature import NGWFeature

from ..utils import ICONS_DIR, log

ADD_FEATURE_URL = u"/api/resource/%s/feature/"
DEL_ALL_FEATURES_URL = u"/api/resource/%s/feature/"


class NGWVectorLayer(NGWResource):
    """ Define ngw vector layer resource

        Geometry types: point, multipoint, linestring, multilinestring, polygon, multipolygon 
        
    """

    type_id = 'vector_layer'
    icon_path = path.join(ICONS_DIR, 'vector_layer.svg')
    type_title = 'NGW Vector Layer'

    UNKNOWN = 0
    POINT = 1
    MULTIPOINT = 2
    LINESTRING = 3
    MULTILINESTRING = 4
    POLYGON = 5
    MULTIPOLYGON = 6

    __GEOMETRIES = {
        "POINT": POINT,
        "MULTIPOINT": MULTIPOINT,
        "LINESTRING": LINESTRING,
        "MULTILINESTRING": MULTILINESTRING,
        "POLYGON": POLYGON,
        "MULTIPOLYGON": MULTIPOLYGON,
    }

    icons = {
        UNKNOWN: "vector_layer_point.svg", 
        POINT: "vector_layer_point.svg",
        MULTIPOINT: "vector_layer_mpoint.svg",
        LINESTRING: "vector_layer_line.svg",
        MULTILINESTRING: "vector_layer_mline.svg",
        POLYGON: "vector_layer_polygon.svg",
        MULTIPOLYGON: "vector_layer_mpolygon.svg",
    }

    FieldTypeString, FieldTypeReal = range(2)

    def __init__(self, resource_factory, resource_json):
        NGWResource.__init__(self, resource_factory, resource_json)

        if self.type_id in self._json:
            if "geometry_type" in self._json[self.type_id]:
                self.set_icon(self.geom_type())

        self._field_defs = {}
        for field_def in self._json.get("feature_layer", {}).get("fields", []):
            self._field_defs[field_def.get("keyname")] = field_def

    def fieldType(self, name):
        field_def = self._field_defs.get(name, {})
        if field_def.get("datatype") == "REAL":
            return self.FieldTypeReal
        elif field_def.get("datatype") == "STRING":
            return self.FieldTypeString

        return None

    # TODO Need refactoring.
    @classmethod
    def create_empty(cls, ngw_resource_parent, display_name):
        display_name_uniq = ngw_resource_parent.generate_unique_child_name(display_name)

        parameters = {
            "resource": {
                "cls": cls.type_id,
                "parent": {
                    "id": ngw_resource_parent.common.id
                },
                "display_name": display_name_uniq,
                "keyname": None,
                "description": None
            },
            "resmeta": {
                "items": {}
            },
            "vector_layer":{
                "srs":{ "id":3857 },
                "geometry_type": "POINT",
                "fields": [
                    {
                        "keyname": "attr",
                        "datatype": "STRING"
                    },
                ]
            }
        }

        connection = ngw_resource_parent._res_factory.connection

        try:
            url = cls.get_api_collection_url()
            result = connection.post(url, params=parameters)
            ngw_resource = NGWVectorLayer(
                ngw_resource_parent._res_factory,
                NGWResource.receive_resource_obj(
                    ngw_resource_parent._res_factory.connection,
                    result['id']
                )
            )

            return ngw_resource

        except requests.exceptions.RequestException, e:
            raise NGWError('Cannot create e,pty vector layer. Server response:\n%s' % e.message)

    def geom_type(self):
        if self.type_id in self._json:
            if "geometry_type" in self._json[self.type_id]:
                return self.__GEOMETRIES.get(self._json[self.type_id]["geometry_type"], self.UNKNOWN)
        return self.UNKNOWN

    def is_geom_multy(self):
        return self.geom_type() in [self.MULTIPOINT, self.MULTILINESTRING, self.MULTIPOLYGON]

    def srs(self):
        return self._json.get(self.type_id, {}).get("srs", {}).get("id")

    def get_geojson_url(self):
        return '%s/%s/' % (
            self.get_absolute_url_with_auth(),
            'geojson'
        )

    def set_icon(self, geometry_type):
        icon_filename = self.icons.get(geometry_type, 'vector_layer.svg')
        self.icon_path = path.join(ICONS_DIR, icon_filename)

    def get_feature_adding_url(self):
        return ADD_FEATURE_URL % self.common.id

    def get_feature_deleting_url(self):
        return DEL_ALL_FEATURES_URL % self.common.id

    # TODO Need refactoring 
    def patch_features(self, ngw_feature_list):
        log ("!!! update_features %s" % ngw_feature_list)
        features_dict_list = []
        for ngw_feature in ngw_feature_list:
            features_dict_list.append(ngw_feature.asDict())

        connection = self._res_factory.connection

        try:
            # connection.delete(self.get_feature_deleting_url())

            url = self.get_feature_adding_url()
            log ("!!! update_features %s" % features_dict_list)
            result = connection.patch(url, params=features_dict_list)
        except requests.exceptions.RequestException, e:
            raise NGWError('Cannot patch vector layer. Server response:\n%s' % e.message)

    def delete_all_features(self):
        connection = self._res_factory.connection
        try:
            connection.delete(self.get_feature_deleting_url())
        except requests.exceptions.RequestException, e:
            raise NGWError('Cannot delete all features from vector layer. Server response:\n%s' % e.message)

    # TODO Need refactoring. Paging loading with process
    def get_features(self):
        connection = self._res_factory.connection

        try:
            url = self.get_feature_adding_url()
            result = connection.get(url)

            ngw_features = []
            for feature in result:
                ngw_features.append(NGWFeature(feature, self))

            return ngw_features
        except requests.exceptions.RequestException, e:
            raise NGWError('Cannot get all features from vector layer. Server response:\n%s' % e.message)

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
        callback - upload file callback
        """
        connection = self._res_factory.connection
        style_name = self.generate_unique_child_name(
            self.common.display_name + '-style'
        )

        try:
            style_file_desc = connection.upload_file(qml, callback)
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

    def add_aliases(self, aliases):
        flayer_dict = self._json.get('feature_layer')
        if flayer_dict is None:
            raise NGWError('Cannot add alias for resource. There is no feature_layer in Resource JSON')

        fields_list = flayer_dict.get('fields')
        if fields_list is None:
            raise NGWError('Cannot add alias for resource. There is no feature_layer-fields in Resource JSON')

        aliases_keynames = aliases.keys()

        for field_index in range(len(fields_list)):
            field_keyname = fields_list[field_index]['keyname']
            if field_keyname in aliases_keynames:
                 flayer_dict['fields'][field_index]['display_name'] = aliases[field_keyname]

        try:
            connection = self._res_factory.connection
            url = self.get_relative_api_url()

            params = dict(
                feature_layer = flayer_dict
            )

            res = connection.put(url, params=params)

            self.update()
        except requests.exceptions.RequestException, e:
            raise NGWError('Cannot add alias for resource. Server response:\n%s' % e.message)