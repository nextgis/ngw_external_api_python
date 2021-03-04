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
FEATURE_URL = lambda res_id, feature_id: '/api/resource/%d/feature/%d' % (res_id, feature_id)
FEATURE_ATTACHMENTS_URL = lambda res_id, feature_id: '/api/resource/%d/feature/%d/attachment/' % (res_id, feature_id)

from ..utils import log


# Need refactoring!
class NGWFeature(object):
    def __init__(self, ngw_feature_dict, ngw_vector_layer):
        self.id = ngw_feature_dict.get("id")
        self.geom_wkt = ngw_feature_dict.get("geom")
        self.ngw_vector_layer = ngw_vector_layer

        self.fields = ngw_feature_dict.get("fields", {})

    def get_feature_url(self):
        return FEATURE_URL(self.ngw_vector_layer.common.id, self.id)
    
    def get_feature_attachmets_url(self):
        return FEATURE_ATTACHMENTS_URL(self.ngw_vector_layer.common.id, self.id)
    
    def get_attachments(self):
        return self.ngw_vector_layer._res_factory.connection.get(self.get_feature_attachmets_url())
    
    def link_attachment(self, uploaded_file_info):
        json_data= dict(file_upload = uploaded_file_info)
        res = self.ngw_vector_layer._res_factory.connection.post(self.get_feature_attachmets_url(), json=json_data)
        return res['id']

    def asDict(self):
        feature_dict = {}
        
        if self.id is not None:
            feature_dict["id"] = self.id

        feature_dict["fields"] = self.fields
        feature_dict["geom"] = self.geom_wkt

        return feature_dict

    def setGeom(self, wkt):
        self.geom_wkt = wkt

    def setFieldAsString(self, name, value):
        self.fields[name] = str(value)

    def setFieldAsInt(self, name, value):
        self.fields[name] = int(value)

    def setFieldAsDouble(self, name, value):
        self.fields[name] = double(value)

