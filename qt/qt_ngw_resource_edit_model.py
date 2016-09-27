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
from PyQt4.QtCore import Qt, QModelIndex

from qt_ngw_resource_item import QNGWResourceItemExt
from qt_ngw_resource_model_job import *
from qt_ngw_resource_base_model import *


class QNGWResourcesModel(QNGWResourcesBaseModel):

    JOB_CREATE_NGW_GROUP_RESOURCE = "CREATE_NGW_GROUP_RESOURCE"
    JOB_DELETE_NGW_RESOURCE = "DELETE_NGW_RESOURCE"
    JOB_CREATE_NGW_WFS_SERVICE = "CREATE_NGW_WFS_SERVICE"
    JOB_CREATE_NGW_WEB_MAP = "CREATE_NGW_WEB_MAP"
    JOB_RENAME_RESOURCE = "RENAME_NGW_RESOURCE"

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

    @modelJobSlot()
    def processJobResult(self, job):
        job_result = job.getResult()

        if job_result is None:
            # TODO Exception
            return

        indexes = {}
        for ngw_resource in job_result.added_resources:
            index = indexes.get(ngw_resource.common.parent.id)
            if index is None:
                index = self.getIndexByNGWResourceId(
                    ngw_resource.common.parent.id,
                    self.index(0, 0, QModelIndex())
                )
                indexes[ngw_resource.common.parent.id] = index

            new_index = self.addNGWResourceToTree(index, ngw_resource)

            if job_result.main_resource_id == ngw_resource.common.id:
                if job.model_response is not None:
                    job.model_response.done.emit(new_index)

        for rid in indexes:
            self.updateResourceWithLoadChildren(indexes[rid])

        for ngw_resource in job_result.edited_resources:
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

            new_index = self.addNGWResourceToTree(index, ngw_resource)

            if job.model_response is not None:
                job.model_response.done.emit(new_index)

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

            if job.model_response is not None:
                job.model_response.done.emit(index)

    @modelRequest()
    def tryCreateNGWGroup(self, new_group_name, parent_index):
        if not parent_index.isValid():
            parent_index = self.index(0, 0, parent_index)

        parent_index = self._nearest_ngw_group_resource_parent(parent_index)

        parent_item = parent_index.internalPointer()
        ngw_resource_parent = parent_item.data(0, parent_item.NGWResourceRole)

        return self._startJob(
            NGWGroupCreater(new_group_name, ngw_resource_parent),
            self.JOB_CREATE_NGW_GROUP_RESOURCE,
            self.processJobResult,
        )

    @modelRequest()
    def deleteResource(self, index):
        item = index.internalPointer()
        ngw_resource = item.data(0, item.NGWResourceRole)

        return self._startJob(
            NGWResourceDelete(ngw_resource),
            self.JOB_DELETE_NGW_RESOURCE,
            self.processJobResult,
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
            NGWCreateWFSForVector(ngw_resource, ngw_parent_resource, ret_obj_num),
            self.JOB_CREATE_NGW_WFS_SERVICE,
            self.processJobResult,
        )

    @modelRequest()
    def createMapForStyle(self, index):
        if not index.isValid():
            index = self.index(0, 0, index)

        item = index.internalPointer()
        ngw_resource = item.data(0, Qt.UserRole)

        return self._startJob(
            NGWCreateMapForStyle(ngw_resource),
            self.JOB_CREATE_NGW_WEB_MAP,
            self.processJobResult,
        )

    @modelRequest()
    def renameResource(self, index, new_name):
        item = index.internalPointer()
        ngw_resource = item.data(0, item.NGWResourceRole)

        return self._startJob(
            NGWRenameResource(ngw_resource, new_name),
            self.JOB_RENAME_RESOURCE,
            self.processJobResult,
        )
