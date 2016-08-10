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
from qt_ngw_resource_model_job import NGWResourceUpdate, NGWRootResourcesLoader, NGWResourcesLoader


class NGWResourcesModelJob(QObject):
    started = pyqtSignal()
    statusChanged = pyqtSignal(unicode)
    errorOccurred = pyqtSignal(object)
    finished = pyqtSignal()

    def __init__(self, parent, job_id, worker):
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
        self.__worker.statusChanged.connect(self.statusChanged.emit)
        self.__worker.errorOccurred.connect(self.errorOccurred.emit)
        self.__worker.finished.connect(self.finished.emit)

        self.__worker.dataReceived.connect(self.__rememberResult)

    def __del__(self):
        self.__worker.started.disconnect()
        self.__worker.statusChanged.disconnect()
        self.__worker.finished.disconnect()
        self.__worker.errorOccurred.disconnect()

    def __rememberResult(self, result):
        self.__result = result

    def getJobId(self):
        return self.__job_id

    def getResult(self):
        return self.__result

    def start(self):
        self.__thread = QThread(self)
        self.__worker.moveToThread(self.__thread)
        self.__worker.finished.connect(self.__thread.deleteLater)
        self.__thread.started.connect(self.__worker.run)

        self.__thread.start()


class QNGWResourcesBaseModel(QAbstractItemModel):
    jobStarted = pyqtSignal(unicode)
    jobStatusChanged = pyqtSignal(unicode, unicode)
    errorOccurred = pyqtSignal(unicode, object)
    jobFinished = pyqtSignal(unicode)

    JOB_NGW_RESOURCE_UPDATE = "RESOURCE_UPDATE"
    JOB_LOAD_NGW_RESOURCE_CHILDREN = "RESOURCES_LOAD"

    def __init__(self, parent):
        QAbstractItemModel.__init__(self, parent)

        # parent.destroyed.connect(self.__stop)

        self.jobs = []

        self.root_item = AuxiliaryItem("Qt model root item")

    def resetModel(self, ngw_connection_settings):
        self.beginResetModel()
        self.__resetModel(ngw_connection_settings)
        self.endResetModel()
        self.modelReset.emit()

    def cleanModel(self):
        self.jobs = []

        c = self.root_item.childCount()
        self.beginRemoveRows(QModelIndex(), 0, c - 1)
        for i in range(c - 1, -1, -1):
            self.root_item.removeChild(self.root_item.child(i))
        self.endRemoveRows()

    def __resetModel(self, ngw_connection_settings):
        self.cleanModel()

        self.beginInsertRows(QModelIndex(), 0, 0)
        self.root_item.addChild(
            AuxiliaryItem("loading...")
        )
        self.endInsertRows()
        self.startLoadRootResources(ngw_connection_settings)

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

        if isinstance(parent_item, QNGWResourceItemExt):
            ngw_resource = parent_item.data(0, QNGWResourceItemExt.NGWResourceRole)
            children_count = ngw_resource.common.children
            return children_count > parent_item.childCount()
        return False

    def fetchMore(self, parent):
        if not parent.isValid():
            parent_item = self.root_item
        else:
            parent_item = parent.internalPointer()

        if isinstance(parent_item, QNGWResourceItemExt):
            self.beginInsertRows(parent, 0, 0)
            parent_item.addChild(
                AuxiliaryItem("loading...")
            )
            self.endInsertRows()
            # self.rowsInserted.emit(parent, 0, 0)
            self.startLoadChildren(parent)

    def columnCount(self, parent=None):
        return 1

    def data(self, index, role=None):
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
            children_count = ngw_resource.common.children
            return children_count > 0

        return parent_item.childCount() > 0

    def flags(self, index):
        if index and index.isValid():
            item = index.internalPointer()
            if not isinstance(item, AuxiliaryItem):
                return Qt.ItemIsEnabled | Qt.ItemIsSelectable

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

    def _stratJobOnNGWResource(self, index, worker, job_id, slots):
        """Registers and starts the job.

            Arguments:
                index -- QModelIndex wich chiled add, edit or deleted
                worker -- The class object inherits from NGWResourceModelJob
                slots -- qt slots will be connected to job finished, last slot must pop job from jobs and call deleteLater
        """
        job = NGWResourcesModelJob(self, job_id, worker)

        job.started.connect(
            self.__jobStartedProcess
        )
        # job.statusChanged.connect(
        #     self.__jobStatusChangedProcess
        # )
        job.finished.connect(
            self.__jobFinishedProcess
        )
        job.errorOccurred.connect(
            self.__jobErrorOccurredProcess
        )

        for slot in slots:
            job.finished.connect(
                slot
            )

        # job.destroyed.connect(self.__job_destroyed)
        job.start()

        self.jobs.append(
            (index, job)
        )

    # def __del__(self):
    #     print "QNGWResourcesBaseModel __del__"
    #     print "self.jobs: ", len(self.jobs)

    def _getJobIndexByJob(self, job):
        for i in range(len(self.jobs)):
            if job is self.jobs[i][1]:
                return i
        return -1

    def __jobStartedProcess(self):
        job_index = self._getJobIndexByJob(self.sender())
        if job_index == -1:
            return

        (index, job) = self.jobs[job_index]
        self.jobStarted.emit(job.getJobId())

    def __jobStatusChangedProcess(self, new_status):
        job_index = self._getJobIndexByJob(self.sender())
        if job_index == -1:
            return

        (index, job) = self.jobs[job_index]
        self.jobStatusChanged.emit(job.getJobId(), new_status)

    def __jobFinishedProcess(self):
        job_index = self._getJobIndexByJob(self.sender())
        if job_index == -1:
            return

        (index, job) = self.jobs[job_index]
        self.jobFinished.emit(job.getJobId())

    def __jobErrorOccurredProcess(self, error):
        job_index = self._getJobIndexByJob(self.sender())
        if job_index == -1:
            return

        (index, job) = self.jobs[job_index]
        self.errorOccurred.emit(job.getJobId(), error)

    def reloadResource(self, index):
        item = self.index.internalPointer()
        ngw_resource = item.data(0, Qt.UserRole)

        worker = NGWResourceUpdate(ngw_resource)
        self._stratJobOnNGWResource(
            index,
            worker,
            self.JOB_NGW_RESOURCE_UPDATE,
            [self.__reloadResourceProcess],
        )

    def __reloadResourceProcess(self):
        # print "__reloadResourceProcess self.jobs: ", self.jobs
        job_index = self._getJobIndexByJob(self.sender())
        if job_index == -1:
            return

        (index, job) = self.jobs.pop(
            job_index
        )

        self.dataChanged.emit(index, index)

    def startLoadRootResources(self, ngw_connection_settings):
        # print "startLoadRootResources"
        worker = NGWRootResourcesLoader(ngw_connection_settings)
        self._stratJobOnNGWResource(
            QModelIndex(),
            worker,
            self.JOB_LOAD_NGW_RESOURCE_CHILDREN,
            # functools.partial(self.__proccessChildrenReceived, QModelIndex()),
            [self.__proccessChildrenReceived],
        )

    def startLoadChildren(self, index):
        item = index.internalPointer()
        ngw_resource = item.data(0, Qt.UserRole)
        worker = NGWResourcesLoader(ngw_resource)
        self._stratJobOnNGWResource(
            index,
            worker,
            self.JOB_LOAD_NGW_RESOURCE_CHILDREN,
            [self.__proccessChildrenReceived],
        )

    def __proccessChildrenReceived(self):
        # print "__proccessChildrenReceived self.jobs: ", self.jobs
        job_index = self._getJobIndexByJob(self.sender())
        if job_index == -1:
            return

        # (index, job) = self.jobs.pop(
        #     job_index
        # )
        (index, job) = self.jobs[job_index]

        if not index.isValid():
            item = self.root_item
        else:
            item = index.internalPointer()

        # Remove servise item - loading...
        for i in range(0, item.childCount()):
            if isinstance(item.child(i), AuxiliaryItem):
                item.removeChild(item.child(i))
                self.rowsRemoved.emit(index, i, i)

        ngw_resources = job.getResult()

        c = item.childCount()
        self.beginInsertRows(index, c, c + len(ngw_resources) - 1)
        item.addChildren(
            [QNGWResourceItemExt(ngw_resource) for ngw_resource in ngw_resources]
        )
        self.endInsertRows()

        #   job.deleteLater()

    def _reloadChildren(self, parent):
        parent_item = parent.internalPointer()
        childCount = parent_item.childCount()

        if childCount > 0:
            self.beginRemoveRows(parent, 0, childCount - 1)
            for i in range(childCount - 1, -1, -1):
                parent_item.removeChild(parent_item.child(i))
            self.endRemoveRows()
            self.rowsRemoved.emit(parent, 0, childCount - 1)

        if self.hasChildren(parent):
            self.beginInsertRows(parent, 0, 0)
            parent_item.addChild(
                AuxiliaryItem("loading...")
            )
            self.endInsertRows()
            self.rowsInserted.emit(parent, 0, 0)

        self.startLoadChildren(parent)
