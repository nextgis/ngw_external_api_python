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
import requests
from .ngw_error import NGWError
from .ngw_group_resource import NGWGroupResource


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
            res = connection.post(url, params=params)
        except requests.exceptions.RequestException, e:
            raise NGWError('Cannot create resource. Server response:\n%s' % e.message)
