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
from qgis.PyQt.QtCore import Qt, QModelIndex

from .qt_ngw_resource_model_job import *
from .qt_ngw_resource_base_model import *

from ..utils import log

class QNGWResourcesModel(QNGWResourcesBaseModel):

    def __init__(self, parent):
        QNGWResourcesBaseModel.__init__(self, parent)

    @modelRequest()
    def tryCreateNGWGroup(self, new_group_name, parent_index):
        if not parent_index.isValid():
            parent_index = self.index(0, 0, parent_index)

        parent_index = self._nearest_ngw_group_resource_parent(parent_index)

        parent_item = parent_index.internalPointer()
        ngw_resource_parent = parent_item.data(0, parent_item.NGWResourceRole)

        return self._startJob(
            NGWGroupCreater(new_group_name, ngw_resource_parent)
        )

    @modelRequest()
    def deleteResource(self, index):
        item = index.internalPointer()
        ngw_resource = item.data(0, item.NGWResourceRole)

        return self._startJob(
            NGWResourceDelete(ngw_resource)
        )

    @modelRequest()
    def createWFSForVector(self, index, ret_obj_num):
        if not index.isValid():
            index = self.index(0, 0, index)

        parent_index = self._nearest_ngw_group_resource_parent(index)

        parent_item = parent_index.internalPointer()
        ngw_parent_resource = parent_item.data(0, Qt.UserRole)

        item = index.internalPointer()
        ngw_resource = item.data(0, Qt.UserRole)

        return self._startJob(
            NGWCreateWFSForVector(ngw_resource, ngw_parent_resource, ret_obj_num)
        )

    @modelRequest()
    def createMapForStyle(self, index):
        if not index.isValid():
            index = self.index(0, 0, index)

        item = index.internalPointer()
        ngw_resource = item.data(0, Qt.UserRole)

        return self._startJob(
            NGWCreateMapForStyle(ngw_resource)
        )

    @modelRequest()
    def renameResource(self, index, new_name):
        item = index.internalPointer()
        ngw_resource = item.data(0, item.NGWResourceRole)

        return self._startJob(
            NGWRenameResource(ngw_resource, new_name)
        )
