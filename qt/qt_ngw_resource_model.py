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
import functools

from PyQt4.QtCore import Qt, QAbstractItemModel, QModelIndex, QVariant, QObject, pyqtSignal, QThread

from qt_ngw_resource_item import QNGWResourceItemExt, AuxiliaryItem
from ..core.ngw_error import NGWError
from ..core.ngw_resource import NGWResource
from ..core.ngw_group_resource import NGWGroupResource
from ..core.ngw_resource_creator import ResourceCreator
from ..core.ngw_resource_factory import NGWResourceFactory


class QNGWResourcesModel(QAbstractItemModel):
    def __init__(self, tree_item):
        QAbstractItemModel.__init__(self)
        self.root = tree_item

    def index(self, row, column, parent_index=None, *args, **kwargs):
        if self.hasIndex(row, column, parent_index):
            parent_item = self._item_by_index(parent_index)
            child_item = parent_item.get_child(row)
            return self.createIndex(row, column, child_item)
        return QModelIndex()

    def parent(self, index=None):
        child_item = self._item_by_index(index)
        parent_item = child_item.parent()
        if parent_item == self.root or not parent_item:
            return QModelIndex()
        return self.createIndex(parent_item.row(), 0, parent_item) #??? WHY parent

    def rowCount(self, parent_index=None, *args, **kwargs):
        parent_item = self._item_by_index(parent_index)
        return parent_item.get_children_count()

    def columnCount(self, parent_index=None, *args, **kwargs):
        return 1

    def data(self, index, role=None):
        if index.isValid():
            return self._item_by_index(index).data(role)
        return QVariant()

    def hasChildren(self, parent_index=None, *args, **kwargs):
        return self._item_by_index(parent_index).has_children()

    def _item_by_index(self, index):
        if index and index.isValid():
            return index.internalPointer()
        else:
            return self.root


class QNGWResourcesModelExt(QAbstractItemModel):
    errorOccurred = pyqtSignal(int, object)

    jobStarted = pyqtSignal(int)
    jobStatusChanged = pyqtSignal(int, unicode)
    jobFinished = pyqtSignal(int)

    JOB_NGW_RESOURCE_UPDATE = 0
    JOB_LOAD_NGW_RESOURCE_CHILDREN = 1
    JOB_CREATE_NGW_GROUP_RESOURCE = 2
    JOB_DELETE_NGW_RESOURCE = 3
    JOB_CREATE_NGW_WFS_SERVICE = 4

    def __init__(self):
        QAbstractItemModel.__init__(self)
        self.workers = []
        self.threads = []

        self.root_item = AuxiliaryItem("Qt model root item")

    def resetModel(self, ngw_connection_settings):
        self.beginResetModel()
        self.__resetModel(ngw_connection_settings)
        self.endResetModel()
        self.modelReset.emit()

    def cleanModel(self):
        c = self.root_item.childCount()
        self.beginRemoveRows(QModelIndex(), 0, c - 1)
        for i in range(c - 1, -1, -1):
            self.root_item.removeChild(self.root_item.child(i))
        self.endRemoveRows()

    def __resetModel(self, ngw_connection_settings):
        # TODO stop all workers
        self.cleanModel()

        try:
            rsc_factory = NGWResourceFactory(ngw_connection_settings)
            ngw_root_resource = rsc_factory.get_root_resource()

            self.root_item.addChild(
                QNGWResourceItemExt(ngw_root_resource)
            )
        except Exception as e:
            self.errorOccurred.emit(self.JOB_LOAD_NGW_RESOURCE_CHILDREN, e)

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
            self.rowsInserted.emit(parent, 0, 0)
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

    def _nearest_ngw_group_resource_parent(self, index):
        checking_index = index
        item = checking_index.internalPointer()
        ngw_resource = item.data(0, QNGWResourceItemExt.NGWResourceRole)
        while not isinstance(ngw_resource, NGWGroupResource):
            checking_index = self.parent(checking_index)
            checking_item = checking_index.internalPointer()
            ngw_resource = checking_item.data(0, QNGWResourceItemExt.NGWResourceRole)

        return checking_index

    def _stratJobOnNGWResource(self, qobject_worker, job, callback, parent_index):
        # TODO clean stoped threads

        thread = QThread(self)
        qobject_worker.moveToThread(thread)
        thread.started.connect(qobject_worker.run)

        qobject_worker.started.connect(
            functools.partial(self.jobStarted.emit, job)
        )
        qobject_worker.statusChanged.connect(
            functools.partial(self.jobStatusChanged.emit, job)
        )
        qobject_worker.finished.connect(
            functools.partial(self.jobFinished.emit, job)
        )

        qobject_worker.errorOccurred.connect(
            functools.partial(self.errorOccurred.emit, job)
        )

        if job == self.JOB_NGW_RESOURCE_UPDATE:
            def processDoneJob(callback, index, ngw_resource):
                item = index.internalPointer()
                item.set_ngw_resource(ngw_resource)
                self.dataChanged.emit(index, index)
                callback()

            qobject_worker.done.connect(
                functools.partial(processDoneJob, callback, parent_index)
            )
        else:
            def processDoneJob(callback, index, *args):
                item = index.internalPointer()
                ngw_resource = item.data(0, item.NGWResourceRole)
                worker = NGWResourceUpdate(ngw_resource)
                self._stratJobOnNGWResource(
                    worker,
                    self.JOB_NGW_RESOURCE_UPDATE,
                    functools.partial(
                        callback,
                        *args
                    ),
                    index)

            qobject_worker.done.connect(
                functools.partial(processDoneJob, callback, parent_index)
            )

        # qobject_worker.finished.connect(thread.quit)
        # qobject_worker.finished.connect(qobject_worker.deleteLater)
        # qobject_worker.finished.connect(thread.deleteLater)

        thread.start()

        self.threads.append(thread)
        self.workers.append(qobject_worker)

    def startLoadChildren(self, index):
        item = index.internalPointer()
        worker = NGWResourcesLoader(item.data(0, Qt.UserRole))
        self._stratJobOnNGWResource(
            worker,
            self.JOB_LOAD_NGW_RESOURCE_CHILDREN,
            functools.partial(self.__proccessChildrenReceived, index),
            index
        )

    def __proccessChildrenReceived(self, index, ngw_resources):
        item = index.internalPointer()

        # Remove servise item - loading...
        for i in range(0, item.childCount()):
            if isinstance(item.child(i), AuxiliaryItem):
                item.removeChild(item.child(i))
                self.rowsRemoved.emit(index, i, i)

        c = item.childCount()
        self.beginInsertRows(index, c, c + len(ngw_resources) - 1)
        item.addChildren(
            [QNGWResourceItemExt(ngw_resource) for ngw_resource in ngw_resources]
        )
        self.endInsertRows()
        self.rowsInserted.emit(index, c, c + len(ngw_resources) - 1)

    def tryCreateNGWGroup(self, new_group_name, parent_index):
        parent_item = parent_index.internalPointer()
        ngw_resource_parent = parent_item.data(0, parent_item.NGWResourceRole)

        if ngw_resource_parent is None:
            return False

        worker = NGWGroupCreater(new_group_name, ngw_resource_parent)
        self._stratJobOnNGWResource(
            worker,
            self.JOB_CREATE_NGW_GROUP_RESOURCE,
            functools.partial(self.__proccessGroupAdded, parent_index),
            parent_index
        )

    def __proccessGroupAdded(self, parent_index, ngw_resource_group):
        self._reloadChildren(parent_index)

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

    def deleteResource(self, index):
        parent_index = self.parent(index)

        item = index.internalPointer()
        ngw_resource = item.data(0, item.NGWResourceRole)

        worker = NGWResourceDelete(ngw_resource)
        self._stratJobOnNGWResource(
            worker,
            self.JOB_DELETE_NGW_RESOURCE,
            functools.partial(self.__proccessResourceDeleted, parent_index),
            parent_index
        )

    def __proccessResourceDeleted(self, parent_index):
        self._reloadChildren(parent_index)

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
            functools.partial(self.__proccessWFSCreate, parent_index),
            parent_index
        )

    def __proccessWFSCreate(self, parent_index):
        self._reloadChildren(parent_index)


class NGWResourceModelJob(QObject):
    started = pyqtSignal()
    statusChanged = pyqtSignal(unicode)
    errorOccurred = pyqtSignal(object)
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


class NGWResourceUpdate(NGWResourceModelJob):
    done = pyqtSignal(object)

    def __init__(self, ngw_resource):
        NGWResourceModelJob.__init__(self)
        self.ngw_resource = ngw_resource

    def run(self):
        self.started.emit()

        try:
            ngw_resource = self.ngw_resource._res_factory.get_resource_by_json(
                NGWResource.receive_resource_obj(
                    self.ngw_resource._res_factory.connection,
                    self.ngw_resource.common.id
                )
            )
            self.done.emit(ngw_resource)

        except Exception as e:
            self.errorOccurred.emit(e)

        self.finished.emit()


class NGWResourcesLoader(NGWResourceModelJob):
    done = pyqtSignal(list)

    def __init__(self, ngw_parent_resource):
        NGWResourceModelJob.__init__(self)
        self.ngw_parent_resource = ngw_parent_resource

    def loadNGWResourceChildren(self):
        try:
            ngw_resource_children = self.ngw_parent_resource.get_children()
            if len(ngw_resource_children) == 0:
                return

            self.done.emit(ngw_resource_children)
        except Exception as e:
            self.errorOccurred.emit(e)

    def run(self):
        self.started.emit()
        self.loadNGWResourceChildren()
        self.finished.emit()


class NGWGroupCreater(NGWResourceModelJob):
    done = pyqtSignal(object)

    def __init__(self, new_group_name, ngw_resource_parent):
        NGWResourceModelJob.__init__(self)
        self.new_group_name = new_group_name
        self.ngw_resource_parent = ngw_resource_parent

    def run(self):
        self.started.emit()
        try:
            chd_names = [ch.common.display_name for ch in self.ngw_resource_parent.get_children()]

            new_group_name = self.generate_unique_name(self.new_group_name, chd_names)

            ngw_group_resource = ResourceCreator.create_group(
                self.ngw_resource_parent,
                new_group_name
            )

            self.done.emit(ngw_group_resource)

        except Exception as e:
            self.errorOccurred.emit(e)

        self.finished.emit()


class NGWResourceDelete(NGWResourceModelJob):
    done = pyqtSignal()

    def __init__(self, ngw_resource):
        NGWResourceModelJob.__init__(self)
        self.ngw_resource = ngw_resource

    def run(self):
        self.started.emit()
        try:
            NGWResource.delete_resource(self.ngw_resource)

            self.done.emit()

        except Exception as e:
            self.errorOccurred.emit(e)

        self.finished.emit()


class NGWCreateWFSForVector(NGWResourceModelJob):
    done = pyqtSignal()

    def __init__(self, ngw_vector_layer, ngw_group_resource, ret_obj_num):
        NGWResourceModelJob.__init__(self)
        self.ngw_vector_layer = ngw_vector_layer
        self.ngw_group_resource = ngw_group_resource
        self.ret_obj_num = ret_obj_num

    def run(self):
        self.started.emit()

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

            self.done.emit()

        except Exception as e:
            self.errorOccurred.emit(e)

        self.finished.emit()
