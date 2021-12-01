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
import os
import uuid

from qgis.PyQt.QtCore import Qt, QAbstractItemModel, QModelIndex, QObject, pyqtSignal, QThread, QCoreApplication

from ..core.ngw_group_resource import NGWGroupResource
from ..utils import log

from .qt_ngw_resource_item import *
from .qt_ngw_resource_model_job import *


class NGWResourcesModelResponse(QObject):
    ErrorCritical = 0
    ErrorWarrning = 1

    done = pyqtSignal(object)

    def __init__(self, parent):
        QObject.__init__(self, parent)

        self.job_id = None
        self.__errors = {}
        self._warnings = []

    def errors(self):
        return self.__errors

    def warnings(self):
        return self._warnings

class NGWResourcesModelJob(QObject):
    started = pyqtSignal()
    statusChanged = pyqtSignal(str)
    warningOccurred = pyqtSignal(object)
    errorOccurred = pyqtSignal(object)
    finished = pyqtSignal()

    def __init__(self, parent, worker, model_response=None):
        """Create job.

            Arguments:
                job_id -- Job identification
                worker -- The class object inherits from NGWResourceModelJob
        """
        QObject.__init__(self, parent)
        self.__result = None
        self.__worker = worker
        self.__job_id = self.__worker.id
        self.__error = None
        self.__warnings = []
        # self.__job_id = "%s_%s" % (self.__worker.id, str(uuid.uuid1()))

        self.__worker.started.connect(self.started.emit)
        self.__worker.dataReceived.connect(self.__rememberResult)
        self.__worker.statusChanged.connect(self.statusChanged.emit)
        self.__worker.errorOccurred.connect(self.processJobError)
        self.__worker.warningOccurred.connect(self.processJobWarnings)

        self.model_response = model_response

    def setResponseObject(self, resp):
        self.model_response = resp
        self.model_response.job_id = self.__job_id

    def __rememberResult(self, result):
        self.__result = result

    def getJobId(self):
        return self.__job_id

    def getResult(self):
        return self.__result

    def error(self):
        return self.__error

    def processJobError(self, job_error):
        self.__error = job_error
        self.errorOccurred.emit(job_error)

    def processJobWarnings(self, job_error):
        if self.model_response:
            self.model_response._warnings.append(job_error)
        # self.warningOccurred.emit(job_error)

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
    jobStarted = pyqtSignal(str)
    jobStatusChanged = pyqtSignal(str, str)
    errorOccurred = pyqtSignal(str, object)
    warningOccurred = pyqtSignal(str, object)
    jobFinished = pyqtSignal(str)
    indexesBlocked = pyqtSignal()
    indexesReleased = pyqtSignal()

    def __init__(self, parent):
        QAbstractItemModel.__init__(self, parent)

        self.__ngw_connection_settings = None
        self._ngw_connection = None

        self.jobs = []
        self.root_item = QNGWConnectionItem()

        self.__indexes_blocked_by_jobs = {}
        self.__indexes_blocked_by_job_errors = {}

    @property
    def connectionSettings(self):
        return self.__ngw_connection_settings

    def isCurrentConnectionSame(self, other):
        return self.__ngw_connection_settings == other

    def isCurruntConnectionSameWoProtocol(self, other):
        if self.__ngw_connection_settings is None:
            if other is None:
                return True
            return False
        return self.__ngw_connection_settings.equalWoProtocol(other)

    def resetModel(self, ngw_connection_settings):
        self.__indexes_blocked_by_jobs = {}
        self.__indexes_blocked_by_job_errors = {}

        self.__ngw_connection_settings = ngw_connection_settings
        self._setNgwConnection()

        self.__cleanModel()
        self.beginResetModel()
        self.root_item = QNGWConnectionItem(self.__ngw_connection_settings)
        self.endResetModel()
        self.modelReset.emit()

    def _setNgwConnection(self):
        self._ngw_connection = NGWConnection(self.__ngw_connection_settings)

    def cleanModel(self):
        self.__cleanModel()

    def __cleanModel(self):
        c = self.root_item.childCount()
        self.beginRemoveRows(QModelIndex(), 0, c - 1)
        for i in range(c - 1, -1, -1):
            self.root_item.removeChild(self.root_item.child(i))
        self.endRemoveRows()

    def item(self, index):
        return index.internalPointer() if index and index.isValid() else self.root_item

    def index(self, row, column, parent):
        # log("--- index" + str(parent.data(QNGWResourceItem.NGWResourceIdRole)))
        if not self.hasIndex(row, column, parent):
            return QModelIndex()

        parent_item = self.item(parent)
        child_item = parent_item.child(row)
        if child_item:
            return self.createIndex(row, column, child_item)
        else:
            return QModelIndex()

    def parent(self, index):
        # log("--- parent" + str(index.data(QNGWResourceItem.NGWResourceIdRole)))
        item = self.item(index)
        parent_item = item.parent()
        if parent_item == self.root_item or not parent_item:
            return QModelIndex()

        return self.createIndex(
            parent_item.parent().indexOfChild(parent_item),
            index.column(),
            parent_item
        )

    def rowCount(self, parent):
        # log("--- rowCount" + str(parent.data(QNGWResourceItem.NGWResourceIdRole)))
        parent_item = self.item(parent)
        return parent_item.childCount()

    def canFetchMore(self, parent):
        log("--- canFetchMore start " + str(parent.data(QNGWResourceItem.NGWResourceIdRole)))
        if self._isIndexBlockedByJob(parent) or self._isIndexBlockedByJobError(parent):
            return False

        item = self.item(parent)
        can_fetch_more = item.ngw_resource_children_count() > item.childCount()
        log("--- canFetchMore finish " + str(parent.data(QNGWResourceItem.NGWResourceIdRole)))
        return can_fetch_more

    def fetchMore(self, parent):
        log("--- fetchMore start" + str(parent.data(QNGWResourceItem.NGWResourceIdRole)))
        self.__updateResourceWithLoadChildren(parent)
        log("--- fetchMore finish" + str(parent.data(QNGWResourceItem.NGWResourceIdRole)))

    def columnCount(self, parent=None):
        return 1

    def data(self, index, role=Qt.DisplayRole):
        item = self.item(index)
        return item.data(index.column(), role)

    def hasChildren(self, parent=None):
        parent_item = self.item(parent)
        if isinstance(parent_item, QNGWResourceItem):
            ngw_resource = parent_item.data(0, QNGWResourceItem.NGWResourceRole)
            return ngw_resource.common.children

        return parent_item.childCount() > 0

    def flags(self, index):
        item = self.item(index)
        return item.flags()

    def _nearest_ngw_group_resource_parent(self, index):
        checking_index = index

        item = checking_index.internalPointer()
        ngw_resource = item.data(0, QNGWResourceItem.NGWResourceRole)

        while not isinstance(ngw_resource, NGWGroupResource):
            checking_index = self.parent(checking_index)
            checking_item = checking_index.internalPointer()
            ngw_resource = checking_item.data(0, QNGWResourceItem.NGWResourceRole)

        return checking_index

    # TODO job должен уметь не стартовать, например есди запущен job обновления дочерних ресурсов - нельзя запускать обновление
    def _startJob(self, worker, index=None, slot=None, response=None):
        """Registers and starts the job.

            Arguments:
                worker -- The class object inherits from NGWResourceModelJob
                slots -- qt slots will be connected to job finished, last slot must call deleteLater
        """
        job = NGWResourcesModelJob(self, worker, response)
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

        if slot is None:
            job.finished.connect(self.processJobResult)
        else:
            job.finished.connect(slot)

        self.jobs.append(job)

        if index is not None:
            self._blockIndexesByJob([index], job)

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
        parent_item = self.item(parent)

        new_item = QNGWResourceItem(ngw_resource)
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

    def _blockIndexesByJob(self, indexes, job):
        if self.__indexes_blocked_by_jobs.get(job) is None:
            self.__indexes_blocked_by_jobs[job] = []
        self.__indexes_blocked_by_jobs[job].extend(indexes)

        for index in indexes:
            item = self.item(index)
            self.beginInsertRows(index, item.childCount(), item.childCount())
            item.lock()
            self.endInsertRows()

        QCoreApplication.processEvents()

        self.indexesBlocked.emit()

    def _releaseIndexesByJob(self, job):
        indexes = self.__indexes_blocked_by_jobs.get(job, [])
        self.__indexes_blocked_by_jobs[job] = []

        for index in indexes:
            item = self.item(index)

            self.beginRemoveRows(index, item.childCount(), item.childCount())
            item.release()
            self.endRemoveRows()

            if job.error() is not None:
                self.__indexes_blocked_by_job_errors[index] = job.error()

        QCoreApplication.processEvents()

        self.indexesReleased.emit()

    def _isIndexBlockedByJob(self, index):
        for job, blocked_indexes in list(self.__indexes_blocked_by_jobs.items()):
            for blocked_index in blocked_indexes:
                if index == blocked_index:
                    return True
        return False

    def _isIndexBlockedByJobError(self, index):
        for blocked_index, error in list(self.__indexes_blocked_by_job_errors.items()):
            if index == blocked_index:
                return True
        return False

    def getIndexByNGWResourceId(self, ngw_resource_id, start_with):
        item = start_with.internalPointer()

        for i in range(0, item.childCount()):
            index = self.getIndexByNGWResourceId(
                ngw_resource_id,
                self.index(i, 0, start_with)
            )

            if index is not None:
                return index

        if isinstance(item, QNGWResourceItem):
            if item.ngw_resource_id() == ngw_resource_id:
                return start_with

        return None

    @modelJobSlot()
    def processJobResult(self, job):
        log("processJobResult job: %s" % job.getJobId())
        job_result = job.getResult()

        if job_result is None:
            # TODO Exception
            self._releaseIndexesByJob(job)
            return

        indexes = {}
        for ngw_resource in job_result.added_resources:
            if ngw_resource.common.parent is None:
                index = QModelIndex()
                new_index = self.addNGWResourceToTree(index, ngw_resource)
            else:
                index = indexes.get(ngw_resource.common.parent.id)
                if index is None:
                    index = self.getIndexByNGWResourceId(
                        ngw_resource.common.parent.id,
                        self.index(0, 0, QModelIndex())
                    )
                    indexes[ngw_resource.common.parent.id] = index

                item = index.internalPointer()
                current_ids = [item.child(i).ngw_resource_id() for i in range(0, item.childCount()) if isinstance(item.child(i), QNGWResourceItem)]
                if ngw_resource.common.id not in current_ids:
                    new_index = self.addNGWResourceToTree(index, ngw_resource)
                else:
                    continue

            if job_result.main_resource_id == ngw_resource.common.id:
                if job.model_response is not None:
                    job.model_response.done.emit(new_index)

        for ngw_resource in job_result.edited_resources:
            if ngw_resource.common.parent is None:
                self.cleanModel() # remove root item
                index = QModelIndex()
            else:
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
                    self._releaseIndexesByJob(job)
                    return

            new_index = self.addNGWResourceToTree(index, ngw_resource)

            if job.model_response is not None:
                job.model_response.done.emit(new_index)

        for ngw_resource in job_result.deleted_resources:
            # log(">>> delete ngw_resource: " + str(ngw_resource))
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
                self._releaseIndexesByJob(job)
                return

            ngw_resource = item.data(0, QNGWResourceItem.NGWResourceRole)
            ngw_resource.update()

            if job.model_response is not None:
                job.model_response.done.emit(index)

        self._releaseIndexesByJob(job)

    def __updateResourceWithLoadChildren(self, index):
        item = self.item(index)

        if not isinstance(item, QNGWItem):
            return

        if item == self.root_item:
            job = self._startJob(
                NGWRootResourcesLoader(self._ngw_connection),
                index
            )
        else:
            ngw_resource = item.data(0, Qt.UserRole)
            job = self._startJob(
                NGWResourceUpdater(ngw_resource),
                index
            )

        return job
