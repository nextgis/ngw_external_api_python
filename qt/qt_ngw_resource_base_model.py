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
from PyQt4.QtCore import Qt, QAbstractItemModel, QModelIndex, QObject, pyqtSignal, QThread

from ..core.ngw_group_resource import NGWGroupResource

from qt_ngw_resource_item import QNGWResourceItemExt, AuxiliaryItem
from qt_ngw_resource_model_job import *


class NGWResourcesModelResponse(QObject):
    ErrorCritical = 0
    ErrorWarrning = 1

    done = pyqtSignal(object)

    def __init__(self, parent):
        QObject.__init__(self, parent)

        self.__errors = {}

    def errors(self):
        return self.__errors


class NGWResourcesModelJob(QObject):
    started = pyqtSignal()
    statusChanged = pyqtSignal(unicode)
    warningOccurred = pyqtSignal(object)
    errorOccurred = pyqtSignal(object)
    finished = pyqtSignal()

    def __init__(self, parent, job_id, worker, model_response=None):
        """Create job.

            Arguments:
                job_id -- Job identification
                worker -- The class object inherits from NGWResourceModelJob
        """
        QObject.__init__(self, parent)
        self.__result = None
        self.__worker = worker
        self.__job_id = job_id

        self.__worker.started.connect(self.started.emit)
        self.__worker.dataReceived.connect(self.__rememberResult)
        self.__worker.statusChanged.connect(self.statusChanged.emit)
        self.__worker.errorOccurred.connect(self.errorOccurred.emit)
        self.__worker.warningOccurred.connect(self.warningOccurred.emit)

        self.model_response = model_response

    def setResponseObject(self, resp):
        self.model_response = resp

    def __rememberResult(self, result):
        self.__result = result

    def getJobId(self):
        return self.__job_id

    def getResult(self):
        return self.__result

    def start(self):
        self.__thread = QThread(self)
        self.__worker.moveToThread(self.__thread)
        self.__worker.finished.connect(self.finishProcess)
        self.__thread.started.connect(self.__worker.run)

        self.__thread.start()

    def finishProcess(self):
        self.__worker.started.disconnect()
        self.__worker.dataReceived.disconnect()
        self.__worker.statusChanged.disconnect()
        self.__worker.errorOccurred.disconnect()
        self.__worker.warningOccurred.disconnect()
        self.__worker.finished.disconnect()

        self.__thread.quit()
        self.__thread.wait()
        self.finished.emit()


class QNGWResourcesModelExeption(Exception):
    def __init__(self, message, ngw_error=None):
        self.message = message
        self.ngw_error = ngw_error

    def __str__(self):
        return self.message


def modelRequest():
    def modelRequestDecorator(method):
        def wrapper(self, *args, **kwargs):
            job = method(self, *args, **kwargs)
            response = NGWResourcesModelResponse(self)
            job.setResponseObject(response)
            return response
        return wrapper
    return modelRequestDecorator


def modelJobSlot():
    def modelJobSlotDecorator(method):
        def wrapper(self):
            job = self.sender()
            method(self, job)
            job.deleteLater()
            self.jobs.remove(job)
        return wrapper
    return modelJobSlotDecorator


class QNGWResourcesBaseModel(QAbstractItemModel):
    jobStarted = pyqtSignal(unicode)
    jobStatusChanged = pyqtSignal(unicode, unicode)
    errorOccurred = pyqtSignal(unicode, object)
    warningOccurred = pyqtSignal(unicode, object)
    jobFinished = pyqtSignal(unicode)

    JOB_NGW_RESOURCE_UPDATE = "RESOURCE_UPDATE"
    JOB_LOAD_NGW_RESOURCE_CHILDREN = "RESOURCES_LOAD"

    def __init__(self, parent):
        QAbstractItemModel.__init__(self, parent)

        self.jobs = []
        self.root_item = AuxiliaryItem("Qt model root item")
        self.__ngw_connection_settings = None

        self.indexes_in_update_state = {}

    def resetModel(self, ngw_connection_settings):
        self.__cleanModel()
        self.__ngw_connection_settings = ngw_connection_settings

        self.beginResetModel()
        self.startLoadRootResources(ngw_connection_settings)
        self.endResetModel()
        self.modelReset.emit()

    def isCurrentConnectionSame(self, connection_settings):
        return self.__ngw_connection_settings == connection_settings

    def cleanModel(self):
        self.__cleanModel()

    def __cleanModel(self):
        c = self.root_item.childCount()
        self.beginRemoveRows(QModelIndex(), 0, c - 1)
        for i in range(c - 1, -1, -1):
            self.root_item.removeChild(self.root_item.child(i))
        self.endRemoveRows()

    def index(self, row, column, parent):
        if not self.hasIndex(row, column, parent):
            return QModelIndex()

        if not parent.isValid():
            parent_item = self.root_item
        else:
            parent_item = parent.internalPointer()

        child_item = parent_item.child(row)
        if child_item:
            return self.createIndex(row, column, child_item)
        else:
            return QModelIndex()

    def parent(self, index):
        if index and index.isValid():
            item = index.internalPointer()
        else:
            item = self.root_item

        parent_item = item.parent()
        if parent_item == self.root_item or not parent_item:
            return QModelIndex()

        return self.createIndex(
            parent_item.parent().indexOfChild(parent_item),
            index.column(),
            parent_item
        )

    def rowCount(self, parent):
        if not parent.isValid():
            parent_item = self.root_item
        else:
            parent_item = parent.internalPointer()

        return parent_item.childCount()

    def canFetchMore(self, parent):
        if not parent.isValid():
            parent_item = self.root_item
        else:
            parent_item = parent.internalPointer()

        for parent in self.indexes_in_update_state:
            return False

        if isinstance(parent_item, QNGWResourceItemExt):
            return parent_item.ngw_resource_children_count() > parent_item.childCount()

        return False

    def fetchMore(self, parent):
        if not parent.isValid():
            parent_item = self.root_item
        else:
            parent_item = parent.internalPointer()

        if isinstance(parent_item, QNGWResourceItemExt):
            self.updateResourceWithLoadChildren(parent)

    def columnCount(self, parent=None):
        return 1

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None

        item = index.internalPointer()
        return item.data(index.column(), role)

    def hasChildren(self, parent=None):
        if not parent.isValid():
            parent_item = self.root_item
        else:
            parent_item = parent.internalPointer()

        if isinstance(parent_item, QNGWResourceItemExt):
            ngw_resource = parent_item.data(0, QNGWResourceItemExt.NGWResourceRole)
            return ngw_resource.common.children

        return parent_item.childCount() > 0

    def flags(self, index):
        if index and index.isValid():
            item = index.internalPointer()
            if not isinstance(item, AuxiliaryItem):
                return item.flags()

        return Qt.NoItemFlags

    def _nearest_ngw_group_resource_parent(self, index):
        checking_index = index

        item = checking_index.internalPointer()
        ngw_resource = item.data(0, QNGWResourceItemExt.NGWResourceRole)

        while not isinstance(ngw_resource, NGWGroupResource):
            checking_index = self.parent(checking_index)
            checking_item = checking_index.internalPointer()
            ngw_resource = checking_item.data(0, QNGWResourceItemExt.NGWResourceRole)

        return checking_index

    def _stratJobOnNGWResource(self, worker, job_id, slot):
        self._startJob(worker, job_id, slot)

    def _startJob(self, worker, job_id, slot, response=None):
        """Registers and starts the job.

            Arguments:
                worker -- The class object inherits from NGWResourceModelJob
                slots -- qt slots will be connected to job finished, last slot must call deleteLater
        """
        job = NGWResourcesModelJob(self, job_id, worker, response)
        job.started.connect(
            self.__jobStartedProcess
        )
        job.statusChanged.connect(
            self.__jobStatusChangedProcess
        )
        job.finished.connect(
            self.__jobFinishedProcess
        )
        job.errorOccurred.connect(
            self.__jobErrorOccurredProcess
        )
        job.warningOccurred.connect(
            self.__jobWarningOccurredProcess
        )

        job.finished.connect(
            slot
        )

        self.jobs.append(job)

        job.start()

        return job

    def __jobStartedProcess(self):
        job = self.sender()
        self.jobStarted.emit(job.getJobId())

    def __jobStatusChangedProcess(self, new_status):
        job = self.sender()
        self.jobStatusChanged.emit(job.getJobId(), new_status)

    def __jobFinishedProcess(self):
        job = self.sender()
        self.jobFinished.emit(job.getJobId())

    def __jobErrorOccurredProcess(self, error):
        job = self.sender()
        self.errorOccurred.emit(job.getJobId(), error)

    def __jobWarningOccurredProcess(self, error):
        job = self.sender()
        self.warningOccurred.emit(job.getJobId(), error)

    def addNGWResourceToTree(self, parent, ngw_resource):
        if not parent.isValid():
            parent_item = self.root_item
        else:
            parent_item = parent.internalPointer()

        new_item = QNGWResourceItemExt(ngw_resource)

        i = -1
        for i in range(0, parent_item.childCount()):
            item = parent_item.child(i)
            if new_item.more_priority(item):
                break
        else:
            i += 1

        self.beginInsertRows(parent, i, i)
        parent_item.insertChild(i, new_item)
        self.endInsertRows()

        return self.index(i, 0, parent)

    def startLoadRootResources(self, ngw_connection_settings):
        self.beginInsertRows(QModelIndex(), 0, 0)
        self.root_item.addChild(
            AuxiliaryItem("loading...")
        )
        self.endInsertRows()

        worker = NGWRootResourcesLoader(ngw_connection_settings)
        self._stratJobOnNGWResource(
            worker,
            self.JOB_LOAD_NGW_RESOURCE_CHILDREN,
            self._proccessRootResourcesReceived,
        )

    @modelJobSlot()
    def _proccessRootResourcesReceived(self, job):
        item = self.root_item

        # Remove servise item - loading...
        for i in range(0, item.childCount()):
            if isinstance(item.child(i), AuxiliaryItem):
                item.removeChild(item.child(i))
                self.rowsRemoved.emit(QModelIndex(), i, i)

        if job.getResult() is None:
            return

        ngw_resources = job.getResult()
        for ngw_resource in ngw_resources:
            self.addNGWResourceToTree(QModelIndex(), ngw_resource)

    @modelRequest()
    def updateResourceWithLoadChildren(self, index):
        item = index.internalPointer()

        if index in self.indexes_in_update_state:
            self.indexes_in_update_state[index] += 1
        else:
            self.indexes_in_update_state[index] = 1

            # Add servise item - loading...
            self.beginInsertRows(index, item.childCount(), item.childCount())
            item.addChild(
                AuxiliaryItem("loading...")
            )
            self.endInsertRows()

        ngw_resource = item.data(0, Qt.UserRole)
        return self._startJob(
            NGWResourceUpdater(ngw_resource),
            self.JOB_LOAD_NGW_RESOURCE_CHILDREN,
            self._updateResource,
        )

    @modelJobSlot()
    def _updateResource(self, job):
        if job.getResult() is not None:
            ngw_resource, ngw_resource_children = job.getResult()

            ngw_resource_id = ngw_resource.common.id

            for index in self.indexes_in_update_state:
                item = index.internalPointer()
                if ngw_resource_id == item.ngw_resource_id():
                    break
            else:
                # TODO exception
                return

            item.set_ngw_resource(ngw_resource)

            current_res_count = item.childCount()
            current_ids = [item.child(i).ngw_resource_id() for i in range(0, current_res_count) if isinstance(item.child(i), QNGWResourceItemExt)]
            for ngw_resource_child in ngw_resource_children:
                chiled_id = ngw_resource_child.common.id
                if chiled_id not in current_ids:
                    self.addNGWResourceToTree(index, ngw_resource_child)

        # Remove servise item - loading...
        for i in range(0, item.childCount()):
            if isinstance(item.child(i), AuxiliaryItem):
                self.beginRemoveRows(index, i, i)
                item.removeChild(item.child(i))
                self.endRemoveRows()

        self.indexes_in_update_state[index] -= 1
        if self.indexes_in_update_state[index] == 0:
            self.indexes_in_update_state.pop(index)
