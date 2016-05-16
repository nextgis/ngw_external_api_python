# -*- coding: utf-8 -*-
"""
/***************************************************************************
 Common Plugins settings

 NextGIS WEB API
                             -------------------
        begin                : 2014-10-31
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
import glob
import zipfile
import tempfile

from PyQt4 import QtCore

from qgis.core import *
from qgis.gui import *

from ..qt.qt_ngw_resource_model import *
from ..qt.qt_ngw_resource_item import *

from ..core.ngw_webmap import NGWWebMapLayer, NGWWebMapGroup, NGWWebMapRoot
from ..core.ngw_resource_creator import ResourceCreator


class QNGWResourcesModel4QGIS(QNGWResourcesModelExt):
    qgisProjectImportStarted = QtCore.pyqtSignal()
    qgisProjectImportFinished = QtCore.pyqtSignal()

    def __init__(self):
        QNGWResourcesModelExt.__init__(self)

    def createNGWLayer(self, qgs_map_layer, parent_index):
        if not parent_index.isValid():
            parent_index = self.index(0, 0, parent_index)

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

    def tryImportCurentQGISProject(self, ngw_group_name, parent_index):
        if not parent_index.isValid():
            parent_index = self.index(0, 0, parent_index)

        parent_item = parent_index.internalPointer()
        ngw_resource_parent = parent_item.data(0, parent_item.NGWResourceRole)

        worker = CurrentQGISProjectImporter(ngw_group_name, ngw_resource_parent)
        thread = QThread(self)

        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.started.connect(self.qgisProjectImportStarted.emit)
        worker.errorOccurred.connect(
            functools.partial(self.errorOccurred.emit, QNGWResourceModelError.CreateGroupError)
        )
        worker.finished.connect(self.qgisProjectImportFinished.emit)
        worker.finished.connect(thread.quit)
        worker.finished.connect(
            functools.partial(self.importFinished, parent_index)
        )
        # worker.finished.connect(worker.deleteLater)
        # worker.finished.connect(thread.deleteLater)
        thread.start()

        self.threads.append(thread)
        self.workers.append(worker)

    def importFinished(self, parent_index):
        self._reloadChildren(parent_index)


class CurrentQGISProjectImporter(QObject):
    started = pyqtSignal()
    errorOccurred = pyqtSignal(unicode)
    finished = pyqtSignal()

    def __init__(self, new_group_name, ngw_resource_parent):
        QObject.__init__(self)
        self.new_group_name = new_group_name
        self.ngw_resource_parent = ngw_resource_parent

    def run(self):
        self.started.emit()

        current_project = QgsProject.instance()

        try:
            chd_names = [ch.common.display_name for ch in self.ngw_resource_parent.get_children()]

            if self.new_group_name in chd_names:
                id = 1
                while(self.new_group_name + str(id) in chd_names):
                    id += 1
                self.new_group_name += str(id)

            ngw_group_resource = ResourceCreator.create_group(
                self.ngw_resource_parent,
                self.new_group_name
            )

            ngw_webmap_root_group = NGWWebMapRoot()

            def process_one_level_of_layers_tree(qgsLayerTreeItems, ngw_resource_group, ngw_webmap_item):
                for qgsLayerTreeItem in qgsLayerTreeItems:

                    if isinstance(qgsLayerTreeItem, QgsLayerTreeLayer):
                        QgsMessageLog.logMessage("Import curent qgis project: layer %s" % qgsLayerTreeItem.layer().name())
                        # progressDlg.setMessage(self.tr("Import layer %s") % qgsLayerTreeItem.layer().name())
                        ngw_vector_layer = self.add_layer(
                            qgsLayerTreeItem.layer(),
                            ngw_resource_group
                        )

                        if ngw_vector_layer is None:
                            continue

                        ngw_style_resource = self.add_style(
                            qgsLayerTreeItem.layer(),
                            ngw_vector_layer
                        )

                        if ngw_style_resource is None:
                            continue

                        ngw_webmap_item.appendChild(
                            NGWWebMapLayer(
                                ngw_style_resource.common.id,
                                qgsLayerTreeItem.layer().name()
                            )
                        )

                    if isinstance(qgsLayerTreeItem, QgsLayerTreeGroup):
                        chd_names = [ch.common.display_name for ch in ngw_resource_group.get_children()]

                        group_name = qgsLayerTreeItem.name()

                        if group_name in chd_names:
                            id = 1
                            while(group_name + str(id) in chd_names):
                                id += 1
                            group_name += str(id)

                        ngw_resource_child_group = ResourceCreator.create_group(
                            ngw_resource_group,
                            group_name
                        )

                        ngw_webmap_child_group = NGWWebMapGroup(group_name)
                        ngw_webmap_item.appendChild(
                            ngw_webmap_child_group
                        )

                        process_one_level_of_layers_tree(
                            qgsLayerTreeItem.children(),
                            ngw_resource_child_group,
                            ngw_webmap_child_group
                        )

            process_one_level_of_layers_tree(
                current_project.layerTreeRoot().children(),
                ngw_group_resource,
                ngw_webmap_root_group
            )

            ngw_webmap_resource = self.add_webmap(
                ngw_group_resource,
                self.new_group_name + u"-webmap",
                ngw_webmap_root_group.children
            )

        except NGWError as e:
            self.errorOccurred.emit(e.message)

        except Exception as e:
            self.errorOccurred.emit(str(e))

        self.finished.emit()

    def add_layer(self, qgs_map_layer, ngw_resource):
        layer_type = qgs_map_layer.type()
        if layer_type == QgsMapLayer.VectorLayer:
            layer_provider = qgs_map_layer.providerType()
            if layer_provider == 'ogr':
                source = self.export_to_shapefile(qgs_map_layer)
                filepath = self.compress_shapefile(source)

                ngw_vector_layer = ResourceCreator.create_vector_layer(
                    ngw_resource,
                    filepath,
                    qgs_map_layer.name()
                )

                os.remove(source)
                os.remove(filepath)
                return ngw_vector_layer

        return None

    def export_to_shapefile(self, qgs_vector_layer):
        tmp = tempfile.mktemp('.shp')
        QgsVectorFileWriter.writeAsVectorFormat(
            qgs_vector_layer,
            tmp,
            'utf-8',
            qgs_vector_layer.crs()
        )
        return tmp

    def compress_shapefile(self, filepath):
        tmp = tempfile.mktemp('.zip')
        basePath = os.path.splitext(filepath)[0]
        baseName = os.path.splitext(os.path.basename(filepath))[0]

        zf = zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED)
        for i in glob.iglob(basePath + '.*'):
            ext = os.path.splitext(i)[1]
            zf.write(i, baseName + ext)

        zf.close()
        return tmp

    def add_style(self, qgs_map_layer, ngw_vector_layer):
        layer_type = qgs_map_layer.type()
        if layer_type == QgsMapLayer.VectorLayer:
            tmp = tempfile.mktemp('.qml')
            msg, saved = qgs_map_layer.saveNamedStyle(tmp)

            ngw_resource = ResourceCreator.create_vector_layer_style(
                ngw_vector_layer,
                tmp,
                qgs_map_layer.name()
            )

            os.remove(tmp)
            return ngw_resource

        return None

    def add_webmap(self, ngw_resource, ngw_webmap_name, ngw_webmap_items):
        ngw_webmap_items_as_dicts = [item.toDict() for item in ngw_webmap_items]
        ngw_resource = ResourceCreator.create_webmap(
            ngw_resource,
            ngw_webmap_name,
            ngw_webmap_items_as_dicts,
        )

        return ngw_resource
