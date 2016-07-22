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

from PyQt4.QtCore import *

from ..core.ngw_resource import NGWResource
from ..core.ngw_resource_creator import ResourceCreator
from ..core.ngw_resource_factory import NGWResourceFactory


class NGWResourceModelJob(QObject):
    started = pyqtSignal()
    statusChanged = pyqtSignal(unicode)
    errorOccurred = pyqtSignal(object)
    dataReceived = pyqtSignal(object)
    finished = pyqtSignal()

    def __init__(self):
        QObject.__init__(self)

    def generate_unique_name(self, name, present_names):
        new_name = name
        id = 1
        if new_name in present_names:
            while(new_name in present_names):
                new_name = name + "(%d)" % id
                id += 1
        return new_name

    def run(self):
        self.started.emit()
        self._do()
        self.finished.emit()

    def _do(self):
        pass


class NGWResourceUpdate(NGWResourceModelJob):
    def __init__(self, ngw_resource):
        NGWResourceModelJob.__init__(self)
        self.ngw_resource = ngw_resource

    def _do(self):
        try:
            self.ngw_resource.update()
        except Exception as e:
            self.errorOccurred.emit(e)


class NGWRootResourcesLoader(NGWResourceModelJob):
    def __init__(self, ngw_connection_settings):
        NGWResourceModelJob.__init__(self)
        self.ngw_connection_settings = ngw_connection_settings

        self.results = None

    def loadNGWRootResource(self):
        try:
            rsc_factory = NGWResourceFactory(self.ngw_connection_settings)
            ngw_root_resource = rsc_factory.get_root_resource()

            self.dataReceived.emit([ngw_root_resource])
        except Exception as e:
            self.errorOccurred.emit(e)

    def _do(self):
        self.loadNGWRootResource()


class NGWResourcesLoader(NGWResourceModelJob):
    def __init__(self, ngw_parent_resource):
        NGWResourceModelJob.__init__(self)
        self.ngw_parent_resource = ngw_parent_resource

    def _do(self):
        try:
            self.ngw_parent_resource.update()
            ngw_resource_children = self.ngw_parent_resource.get_children()

            self.dataReceived.emit(ngw_resource_children)
        except Exception as e:
            self.errorOccurred.emit(e)


class NGWGroupCreater(NGWResourceModelJob):
    def __init__(self, new_group_name, ngw_resource_parent):
        NGWResourceModelJob.__init__(self)
        self.new_group_name = new_group_name
        self.ngw_resource_parent = ngw_resource_parent

    def _do(self):
        try:
            chd_names = [ch.common.display_name for ch in self.ngw_resource_parent.get_children()]

            new_group_name = self.generate_unique_name(self.new_group_name, chd_names)

            ngw_group_resource = ResourceCreator.create_group(
                self.ngw_resource_parent,
                new_group_name
            )

            self.dataReceived.emit(ngw_group_resource)

        except Exception as e:
            self.errorOccurred.emit(e)


class NGWResourceDelete(NGWResourceModelJob):
    def __init__(self, ngw_resource):
        NGWResourceModelJob.__init__(self)
        self.ngw_resource = ngw_resource

    def _do(self):
        try:
            NGWResource.delete_resource(self.ngw_resource)
        except Exception as e:
            self.errorOccurred.emit(e)


class NGWCreateWFSForVector(NGWResourceModelJob):
    def __init__(self, ngw_vector_layer, ngw_group_resource, ret_obj_num):
        NGWResourceModelJob.__init__(self)
        self.ngw_vector_layer = ngw_vector_layer
        self.ngw_group_resource = ngw_group_resource
        self.ret_obj_num = ret_obj_num

    def _do(self):
        try:
            ngw_wfs_service_name = self.ngw_vector_layer.common.display_name + "-wfs-service"

            chd_names = [ch.common.display_name for ch in self.ngw_group_resource.get_children()]

            ngw_wfs_service_name = self.generate_unique_name(ngw_wfs_service_name, chd_names)

            ResourceCreator.create_wfs_service(
                ngw_wfs_service_name,
                self.ngw_group_resource,
                [self.ngw_vector_layer],
                self.ret_obj_num
            )
        except Exception as e:
            self.errorOccurred.emit(e)
