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

API_RESOURCE_URL = lambda res_id: '/api/resource/%d' % res_id
API_COLLECTION_URL = '/api/resource/'
RESOURCE_URL = lambda res_id: '/resource/%d' % res_id

class Wrapper():
    def __init__(self, **params):
        self.__dict__.update(params)

DICT_TO_OBJ = lambda d: Wrapper(**d)
LIST_DICT_TO_LIST_OBJ = lambda l: [Wrapper(**el) for el in l]


class NGWResource():

    type_id = 'resource'
    icon_path = path.join(path.dirname(__file__), path.pardir, 'icons/', 'resource.svg')
    type_title = 'NGW Resource'


    # STATIC
    @classmethod
    def receive_resource_obj(cls, ngw_con, res_id):
        """
        :rtype : json obj
        """
        return ngw_con.get(API_RESOURCE_URL(res_id))

    @classmethod
    def receive_resource_children(cls, ngw_con, res_id):
        """
        :rtype : json obj
        """
        return ngw_con.get("%s/?parent=%s" % (API_COLLECTION_URL, res_id))


    # INSTANCE
    def __init__(self, resource_factory, resource_json):
        """
        Init resource from json representation
        :param ngw_resource: any ngw_resource
        """
        self._res_factory = resource_factory
        self._json = resource_json
        self._construct()


    def _construct(self):
        """
        Construct resource from self._json
        Can be overridden in a derived class
        """
        #resource
        self.common = DICT_TO_OBJ(self._json['resource'])
        if self.common.parent:
            self.common.parent = DICT_TO_OBJ(self.common.parent)
        if self.common.owner_user:
            self.common.owner_user = DICT_TO_OBJ(self.common.owner_user)
        #resmeta
        self.metadata = DICT_TO_OBJ(self._json['resmeta'])

    def get_parent(self):
        if self.common.parent:
            return self._res_factory.get_resource(self.common.parent.id)
        else:
            return None

    def get_children(self):
        children = []
        if self.common.children:
            children_json = NGWResource.receive_resource_children(self._res_factory.connection, self.common.id)
            for child_json in children_json:
                children.append(self._res_factory.get_resource_by_json(child_json))
        return children

    def get_absolute_url(self):
        return self._res_factory.connection.server_url + RESOURCE_URL(self.common.id)

    def get_absolute_url_with_auth(self):
        creds = self._res_factory.connection.get_auth()
        return self._res_factory.connection.server_url.replace('://', '://%s:%s@' % creds) + RESOURCE_URL(self.common.id)
