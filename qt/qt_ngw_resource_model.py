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
from PyQt4.QtGui import QTreeWidgetItem
from qgis.core import QgsMessageLog

from qt_ngw_resource_item import QNGWResourceItemExt


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
        # QgsMessageLog.logMessage(">>> QNGWResourcesModel:parent")
        child_item = self._item_by_index(index)
        parent_item = child_item.parent()
        if parent_item == self.root or not parent_item:
            return QModelIndex()
        return self.createIndex(parent_item.row(), 0, parent_item) #??? WHY parent

    def rowCount(self, parent_index=None, *args, **kwargs):
        #QgsMessageLog.logMessage(">>> rowCount parent_index=(%d, %d)" % (parent_index.row(), parent_index.column()))
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
    def __init__(self, ngw_resource):
        QAbstractItemModel.__init__(self)

        self.__resetModel(ngw_resource)

    def resetModel(self, ngw_resource):
        self.beginResetModel()
        self.__clear()
        self.__resetModel(ngw_resource)
        self.endResetModel()
        self.modelReset.emit()

    def __resetModel(self, ngw_resource):
        self.rootItem = QTreeWidgetItem()
        first_item = QNGWResourceItemExt(ngw_resource)
        self.rootItem.addChild(first_item)

        # TODO stop all workers
        self.workers = []
        self.threads = []

    def index(self, row, column, parent):
        if not self.hasIndex(row, column, parent):
            return QModelIndex()

        if not parent.isValid():
            parentItem = self.rootItem
        else:
            parentItem = parent.internalPointer()

        childItem = parentItem.child(row)
        if childItem:
            return self.createIndex(row, column, childItem)
        else:
            return QModelIndex()

    def parent(self, index):
        if not index.isValid():
            return QModelIndex()
        childItem = index.internalPointer()
        parentItem = childItem.parent()
        if parentItem == self.rootItem:
            return QModelIndex()

        return self.createIndex(parentItem.parent().indexOfChild(parentItem), index.column(), parentItem)

    def rowCount(self, parent):
        # QgsMessageLog.logMessage("rowCount")
        if not parent.isValid():
            parentItem = self.rootItem
        else:
            parentItem = parent.internalPointer()

        # QgsMessageLog.logMessage("rowCount: %s" % str(parentItem))
        if isinstance(parentItem, QNGWResourceItemExt):
            if parentItem.data(0, Qt.UserRole + 1) == parentItem.CHILDREN_NOT_LOAD:
                parentItem.addChild(QTreeWidgetItem([self.tr("load...")]))
                self.startLoadChildren(parent)
                parentItem.setData(0, Qt.UserRole + 1, parentItem.CHILDREN_LOADED)

        return parentItem.childCount()

    def columnCount(self, parent=None, *args, **kwargs):
        return 1

    def data(self, index, role=None):
        # QgsMessageLog.logMessage("Data")
        if not index.isValid():
            return None

        # QgsMessageLog.logMessage("Index %d; %d" % (index.row(), index.column()))

        if role not in [Qt.DisplayRole, Qt.DecorationRole, Qt.ToolTipRole, Qt.UserRole]:
            return None

        item = index.internalPointer()
        return item.data(index.column(), role)

    def hasChildren(self, parent=None):
        if not parent.isValid():
            return True
        else:
            parentItem = parent.internalPointer()

        if isinstance(parentItem, QNGWResourceItemExt):
            return parentItem.has_children()
        else:
            return False

    def startLoadChildren(self, index):
        item = index.internalPointer()

        worker = NGQResourcesLoader(item.data(0, Qt.UserRole))
        thread = QThread(self)

        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.resourcesReceived.connect(
            functools.partial(self.proccessChildrenReceived, index)
        )
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        worker.finished.connect(thread.deleteLater)
        worker.finished.connect(lambda: QgsMessageLog.logMessage("Worker finished"))
        thread.start()

        self.threads.append(thread)
        self.workers.append(worker)

    def proccessChildrenReceived(self, index, ngw_resources):
        item = index.internalPointer()

        # Remove servise item - loading...
        item.removeChild(item.child(0))

        item.addChildren(
            [QNGWResourceItemExt(ngw_resource) for ngw_resource in ngw_resources]
        )

        self.rowsInserted.emit(index, 0, len(ngw_resources))


class NGQResourcesLoader(QObject):

    started = pyqtSignal()
    resourcesReceived = pyqtSignal(list)
    finished = pyqtSignal()

    def __init__(self, ngw_resource):
        QObject.__init__(self)
        self.ngw_resource = ngw_resource

    def loadNGWResourceChildren(self):
        ngw_resource_children = self.ngw_resource.get_children()
        if len(ngw_resource_children) == 0:
            return

        self.resourcesReceived.emit(ngw_resource_children)

    def run(self):
        self.started.emit()

        self.loadNGWResourceChildren()

        self.finished.emit()
