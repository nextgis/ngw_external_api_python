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

from PyQt4.QtCore import Qt, QModelIndex, pyqtSignal

from qt_ngw_resource_item import QNGWResourceItemExt
from qt_ngw_resource_model_job import *
from qt_ngw_resource_base_model import QNGWResourcesBaseModel


class QNGWResourcesModel(QNGWResourcesBaseModel):

    focusedResource = pyqtSignal(QModelIndex)

    JOB_CREATE_NGW_GROUP_RESOURCE = "CREATE_NGW_GROUP_RESOURCE"
    JOB_DELETE_NGW_RESOURCE = "DELETE_NGW_RESOURCE"
    JOB_CREATE_NGW_WFS_SERVICE = "CREATE_NGW_WFS_SERVICE"
    JOB_CREATE_NGW_WEB_MAP = "CREATE_NGW_WEB_MAP"

    def __init__(self, parent):
        QNGWResourcesBaseModel.__init__(self, parent)

    def getIndexByNGWResourceId(self, ngw_resource_id, start_with):
        item = start_with.internalPointer()

        for i in range(0, item.childCount()):
            index = self.getIndexByNGWResourceId(
                ngw_resource_id,
                self.index(i, 0, start_with)
            )

            if index is not None:
                return index

        if isinstance(item, QNGWResourceItemExt):
            if item.ngw_resource_id() == ngw_resource_id:
                return start_with

        return None

    def processJobResult(self):
        job = self.jobs.pop(
            self.jobs.index(self.sender())
        )
        job_result = job.getResult()

        if job_result is None:
            # TODO Exception
            return

        indexes = []
        for ngw_resource in job_result.added_resources:
            index = self.getIndexByNGWResourceId(
                ngw_resource.common.parent.id,
                self.index(0, 0, QModelIndex())
            )
            item = index.internalPointer()

            new_index = self.addNGWResourceToTree(index, ngw_resource)

            if job_result.main_resource_id == ngw_resource.common.id:
                self.focusedResource.emit(
                    new_index
                )

            if index not in indexes:
                indexes.append(index)

        for index in indexes:
            self.updateResourceWithLoadChildren(index)

        for ngw_resource in job_result.deleted_resources:
            index = self.getIndexByNGWResourceId(
                ngw_resource.common.parent.id,
                self.index(0, 0, QModelIndex())
            )
            item = index.internalPointer()

            for i in range(0, item.childCount()):
                if item.child(i).ngw_resource_id() == ngw_resource.common.id:
                    self.beginRemoveRows(index, i, i)
                    item.removeChild(item.child(i))
                    self.endRemoveRows()
                    break
            else:
                # TODO exception: not find deleted resource in corrent tree
                return

            if job_result.main_resource_id == ngw_resource.common.id:
                self.focusedResource.emit(index)

            self.updateResourceWithLoadChildren(index)

    def tryCreateNGWGroup(self, new_group_name, parent_index):
        if not parent_index.isValid():
            parent_index = self.index(0, 0, parent_index)

        parent_index = self._nearest_ngw_group_resource_parent(parent_index)

        parent_item = parent_index.internalPointer()
        ngw_resource_parent = parent_item.data(0, parent_item.NGWResourceRole)

        if ngw_resource_parent is None:
            return False

        worker = NGWGroupCreater(new_group_name, ngw_resource_parent)
        self._stratJobOnNGWResource(
            worker,
            self.JOB_CREATE_NGW_GROUP_RESOURCE,
            self.processJobResult,
        )

    def deleteResource(self, index):
        item = index.internalPointer()
        ngw_resource = item.data(0, item.NGWResourceRole)

        worker = NGWResourceDelete(ngw_resource)
        self._stratJobOnNGWResource(
            worker,
            self.JOB_DELETE_NGW_RESOURCE,
            self.processJobResult,
        )

    def createWFSForVector(self, index, ret_obj_num):
        if not index.isValid():
            index = self.index(0, 0, index)

        parent_index = self._nearest_ngw_group_resource_parent(index)

        parent_item = parent_index.internalPointer()
        ngw_parent_resource = parent_item.data(0, Qt.UserRole)

        item = index.internalPointer()
        ngw_resource = item.data(0, Qt.UserRole)

        worker = NGWCreateWFSForVector(ngw_resource, ngw_parent_resource, ret_obj_num)
        self._stratJobOnNGWResource(
            worker,
            self.JOB_CREATE_NGW_WFS_SERVICE,
            self.processJobResult,
        )

    def createMapForStyle(self, index):
        if not index.isValid():
            index = self.index(0, 0, index)

        item = index.internalPointer()
        ngw_resource = item.data(0, Qt.UserRole)

        worker = NGWCreateMapForStyle(ngw_resource)
        self._stratJobOnNGWResource(
            worker,
            self.JOB_CREATE_NGW_WEB_MAP,
            self.processJobResult,
        )
