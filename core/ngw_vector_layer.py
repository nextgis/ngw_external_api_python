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
import datetime

from typing import List


from .ngw_abstract_vector_resource import NGWAbstractVectorResource
from .ngw_resource import API_LAYER_EXTENT, NGWResource
from .ngw_qgis_style import NGWQGISVectorStyle
from .ngw_mapserver_style import NGWMapServerStyle
from .ngw_feature import NGWFeature

ADD_FEATURE_URL = "/api/resource/%s/feature/"
DEL_ALL_FEATURES_URL = "/api/resource/%s/feature/"


class NGWVectorLayer(NGWAbstractVectorResource):
    """Define ngw vector layer resource

    Geometry types: point, multipoint, linestring, multilinestring, polygon, multipolygon

    """

    type_id = "vector_layer"

    def srs(self):
        return self._json.get(self.type_id, {}).get("srs", {}).get("id")

    def get_absolute_geojson_url(self):
        return "{url}/geojson".format(
            url=self.get_absolute_api_url_with_auth()
        )

    def get_feature_adding_url(self):
        return ADD_FEATURE_URL % self.common.id

    def get_feature_deleting_url(self):
        return DEL_ALL_FEATURES_URL % self.common.id

    # TODO Need refactoring
    def patch_features(self, ngw_feature_list):
        features_dict_list = []
        for ngw_feature in ngw_feature_list:
            features_dict_list.append(ngw_feature.asDict())

        connection = self._res_factory.connection

        url = self.get_feature_adding_url()
        result = connection.patch(url, params=features_dict_list)

    def construct_ngw_feature_as_json(self, attributes):
        json_feature = {}

        for field_name, pyvalue in list(attributes.items()):
            field_type = self.fieldType(field_name)
            field_value = None
            if field_type == NGWVectorLayer.FieldTypeDate:
                if isinstance(pyvalue, datetime.date):
                    field_value = {
                        "year": pyvalue.year,
                        "month": pyvalue.month,
                        "day": pyvalue.day,
                    }
            elif field_type == NGWVectorLayer.FieldTypeTime:
                if isinstance(pyvalue, datetime.time):
                    field_value = {
                        "hour": pyvalue.hour,
                        "minute": pyvalue.minute,
                        "second": pyvalue.second,
                    }
            elif field_type == NGWVectorLayer.FieldTypeDatetime:
                if isinstance(pyvalue, datetime.datetime):
                    field_value = {
                        "year": pyvalue.year,
                        "month": pyvalue.month,
                        "day": pyvalue.day,
                        "hour": pyvalue.hour,
                        "minute": pyvalue.minute,
                        "second": pyvalue.second,
                    }
            elif field_type is None:
                field_value = None
            else:
                field_value = pyvalue

            json_feature[field_name] = field_value

        return json_feature

    def delete_all_features(self):
        connection = self._res_factory.connection
        connection.delete(self.get_feature_deleting_url())

    # TODO Need refactoring. Paging loading with process
    def get_features(self) -> List[NGWFeature]:
        connection = self._res_factory.connection

        url = self.get_feature_adding_url()
        result = connection.get(url)

        ngw_features = []
        for feature in result:
            ngw_features.append(NGWFeature(feature, self))

        return ngw_features

    def extent(self):
        result = self._res_factory.connection.get(
            API_LAYER_EXTENT(self.common.id)
        )
        extent = result.get("extent")
        if extent is None:
            return (-180, 180, -90, 90)

        return (
            extent.get("minLon", -180),
            extent.get("maxLon", 180),
            extent.get("minLat", -90),
            extent.get("maxLat", 90),
        )

    def create_qml_style(
        self, qml, callback, style_name=None
    ) -> NGWQGISVectorStyle:
        """Create QML style for this layer

        qml - full path to qml file
        callback - upload file callback
        """
        connection = self._res_factory.connection
        if not style_name:
            style_name = self.common.display_name
        style_name = self.generate_unique_child_name(style_name)

        style_file_desc = connection.upload_file(qml, callback)

        params = dict(
            resource=dict(
                cls=NGWQGISVectorStyle.type_id,
                parent=dict(id=self.common.id),
                display_name=style_name,
            ),
        )
        params[NGWQGISVectorStyle.type_id] = dict(file_upload=style_file_desc)

        url = self.get_api_collection_url()
        result = connection.post(url, params=params)
        ngw_resource = NGWQGISVectorStyle(
            self._res_factory,
            NGWResource.receive_resource_obj(connection, result["id"]),
        )

        return ngw_resource

    def create_map_server_style(self):
        """Create default Map Srver style for this layer"""
        connection = self._res_factory.connection

        style_name = self.generate_unique_child_name(
            self.common.display_name + ""
        )

        params = dict(
            resource=dict(
                cls=NGWMapServerStyle.type_id,
                parent=dict(id=self.common.id),
                display_name=style_name,
            ),
        )

        url = self.get_api_collection_url()
        result = connection.post(url, params=params)
        ngw_resource = NGWMapServerStyle(
            self._res_factory,
            NGWResource.receive_resource_obj(connection, result["id"]),
        )

        return ngw_resource

    def add_aliases(self, aliases):
        flayer_dict = self._json.get("feature_layer")
        # if flayer_dict is None:
        #     raise NGWError('Cannot add alias for resource. There is no feature_layer in Resource JSON')

        fields_list = flayer_dict.get("fields")
        # if fields_list is None:
        #     raise NGWError('Cannot add alias for resource. There is no feature_layer-fields in Resource JSON')

        aliases_keynames = list(aliases.keys())

        for field_index in range(len(fields_list)):
            field_keyname = fields_list[field_index]["keyname"]
            if field_keyname in aliases_keynames:
                flayer_dict["fields"][field_index]["display_name"] = aliases[
                    field_keyname
                ]

        connection = self._res_factory.connection
        url = self.get_relative_api_url()

        params = dict(feature_layer=flayer_dict)

        res = connection.put(url, params=params)

        self.update()

    def export(self, path: str, format: str = "GPKG", srs: int = 3857) -> None:
        url = self.get_relative_api_url()
        export_url = (
            f"{url}/export?format={format}&srs={srs}&fid=&zipped=false"
        )

        connection = self._res_factory.connection
        connection.download(export_url, path)
