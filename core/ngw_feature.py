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
FEATURE_ATTACHMENT_URL = lambda res_id, feature_id, attachment_id: '/api/resource/%d/feature/%d/attachment/%d' % (res_id, feature_id, attachment_id)
IMAGE_URL = lambda res_id, feature_id, image_id: '/api/resource/%s/feature/%d/attachment/%d/image' % (res_id, feature_id, image_id)

class NGWFeature(object):
    def __init__(self, feature_id, ngw_vector_layer):
        self.id = feature_id
        self.ngw_resource = ngw_vector_layer
    
    def get_feature_url(self):
        return FEATURE_URL(self.ngw_resource.common.id, self.id)
    
    def get_feature_attachmets_url(self):
        return FEATURE_ATTACHMENTS_URL(self.ngw_resource.common.id, self.id)
    
    def get_feature_attachmet_url(self, attachment_id):
        return FEATURE_ATTACHMENT_URL(self.ngw_resource.common.id, self.id, attachment_id)
    
    def get_image_url(self, image_id):
        return IMAGE_URL(self.ngw_resource.common.id, self.id, image_id)
    
    def get_image_full_url(self, image_id):
        return self.ngw_resource._res_factory.connection.server_url + self.get_image_url(image_id)
    
    def get_attachments_ids(self):
        return self.ngw_resource._res_factory.connection.get(self.get_feature_attachmets_url())
    
    def link_attachment(self, uploaded_attachment_info):
        json_data= dict(file_upload = uploaded_attachment_info)
        self.ngw_resource._res_factory.connection.post(self.get_feature_attachmets_url(), json=json_data)
    
    def unlink_attachment(self, attachment_id):
        self.ngw_resource._res_factory.connection.delete(self.get_feature_attachmet_url(attachment_id))