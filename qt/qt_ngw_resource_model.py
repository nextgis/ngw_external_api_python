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
from ..core.ngw_resource_creator import ResourceCreator
from ..core.ngw_resource_factory import NGWResourceFactory


from qgis.core import *
from qgis.gui import *

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
    def __init__(self, ngw_connection_settings):
        QAbstractItemModel.__init__(self)

        self.__resetModel(ngw_connection_settings)

    def resetModel(self, ngw_connection_settings):
        self.beginResetModel()
        self.__clear()
        self.__resetModel(ngw_connection_settings)
        self.endResetModel()
        self.modelReset.emit()

    def __resetModel(self, ngw_connection_settings):
        rsc_factory = NGWResourceFactory(ngw_connection_settings)
        ngw_root_resource = rsc_factory.get_root_resource()

        self.root_item = AuxiliaryItem("Qt root item")
        self.root_item.addChild(
            QNGWResourceItemExt(ngw_root_resource)
        )

        # TODO stop all workers
        self.workers = []
        self.threads = []

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

        if isinstance(parent_item, QNGWResourceItemExt):
            if parent_item.data(0, parent_item.NGWResourceChildrenLoadRole) == parent_item.CHILDREN_NOT_LOAD:
                parent_item.addChild(
                    AuxiliaryItem(self.tr("loading..."))
                )
                self.startLoadChildren(parent)
                parent_item.setData(0, parent_item.NGWResourceChildrenLoadRole, parent_item.CHILDREN_LOADED)

        return parent_item.childCount()

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

        if parent_item == self.root_item:
            return True

        if isinstance(parent_item, AuxiliaryItem):
            return False

        return parent_item.has_children()

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

    def createGroupInResource(self, new_group_name, parent_index):
        self.rowCount(parent_index)

        parent_item = parent_index.internalPointer()
        ngw_resource_parent = parent_item.data(0, Qt.UserRole)

        existing_chd_names = [ch.common.display_name for ch in ngw_resource_parent.get_children()]
        existing_chd_count = len(existing_chd_names)

        if new_group_name in existing_chd_names:
            id = 1
            while(new_group_name + str(id) in existing_chd_names):
                id += 1
            new_group_name += str(id)

        try:
            ngw_group_resource = ResourceCreator.create_group(
                ngw_resource_parent,
                new_group_name
            )
        except NGWError:
            # error_mes = ex.message or ''
            return None

        self.beginInsertRows(parent_index, existing_chd_count + 1, existing_chd_count + 1)
        item = QNGWResourceItemExt(ngw_group_resource)
        parent_item.addChild(item)
        self.endInsertRows()

        self.rowsInserted.emit(parent_index, existing_chd_count + 1, existing_chd_count + 1)

        ngw_group_index = self.createIndex(existing_chd_count + 1, parent_index.column(), item)

        QgsMessageLog.logMessage("ngw_group_index: %s" % str(ngw_group_index))
        QgsMessageLog.logMessage("ngw_group_index.internalPointer: %s" % str(ngw_group_index.internalPointer()))

        return (ngw_group_resource, ngw_group_index)

    def createNGWLayer(self, qgs_map_layer, parent_index):
        import os, tempfile, glob, zipfile

        def export_to_shapefile(qgs_vector_layer):
            tmp = tempfile.mktemp('.shp')
            QgsVectorFileWriter.writeAsVectorFormat(
                qgs_vector_layer,
                tmp,
                'utf-8',
                qgs_vector_layer.crs()
            )
            return tmp


        def compress_shapefile(filepath):
            tmp = tempfile.mktemp('.zip')
            basePath = os.path.splitext(filepath)[0]
            baseName = os.path.splitext(os.path.basename(filepath))[0]

            zf = zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED)
            for i in glob.iglob(basePath + '.*'):
                ext = os.path.splitext(i)[1]
                zf.write(i, baseName + ext)

            zf.close()
            return tmp

        self.rowCount(parent_index)
        parent_item = parent_index.internalPointer()
        ngw_resource_parent = parent_item.data(0, Qt.UserRole)
        childer_count = len(ngw_resource_parent.get_children())
 
        layer_type = qgs_map_layer.type()
        if layer_type == qgs_map_layer.VectorLayer:
            layer_provider = qgs_map_layer.providerType()
            if layer_provider == 'ogr':
                source = export_to_shapefile(qgs_map_layer)
                filepath = compress_shapefile(source)

                ngw_vector_layer = ResourceCreator.create_vector_layer(
                    ngw_resource_parent,
                    filepath,
                    qgs_map_layer.name()
                )

                os.remove(source)
                os.remove(filepath)

                self.beginInsertRows(parent_index, childer_count + 1, childer_count + 1)
                item = QNGWResourceItemExt(ngw_vector_layer)
                parent_item.addChild(item)
                self.endInsertRows()
                self.rowsInserted.emit(parent_index, childer_count + 1, childer_count + 1)

                return (ngw_vector_layer, item)

        return None

    def deleteResource(self, index):
        item = index.internalPointer()
        parent_index = self.parent(index)
        parent_item = parent_index.internalPointer()

        if index.isValid():
            ngw_resource = index.data(Qt.UserRole)
            try:
                NGWResource.delete_resource(ngw_resource)
                self.beginRemoveRows(
                    parent_index,
                    index.row(),
                    index.row()
                )
                parent_item.removeChild(item)
                self.endRemoveRows()
                self.rowsRemoved.emit(
                    parent_index,
                    index.row(),
                    index.row()
                )

            except NGWError:
                # print 'Unable to delete resource  with id %d: %s' % (ngw_resource.common.id, e.message)
                # QgsMessageLog.logMessage(
                #     'Unable to delete resource  with id %d: %s' % (ngw_resource.common.id, e.message),
                #     'NGW Connect',
                #     QgsMessageLog.CRITICAL
                # )
                pass


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
