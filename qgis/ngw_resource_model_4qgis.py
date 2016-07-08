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
import functools

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

    JOB_IMPORT_QGIS_RESOURCE = 100
    JOB_IMPORT_QGIS_PROJECT = 101

    def __init__(self):
        QNGWResourcesModelExt.__init__(self)

    def createNGWLayer(self, qgs_map_layer, parent_index):
        if not parent_index.isValid():
            parent_index = self.index(0, 0, parent_index)

        parent_index = self._nearest_ngw_group_resource_parent(parent_index)

        parent_item = parent_index.internalPointer()
        ngw_parent_resource = parent_item.data(0, Qt.UserRole)

        worker = QGISResourceImporter(qgs_map_layer, ngw_parent_resource)
        self._stratJobOnNGWResource(
            worker,
            self.JOB_IMPORT_QGIS_RESOURCE,
            functools.partial(self.__resourceImportFinished, parent_index),
            parent_index
        )

    def __resourceImportFinished(self, parent_index, ngw_resource):
        self._reloadChildren(parent_index)

    def tryImportCurentQGISProject(self, ngw_group_name, parent_index, iface):
        if not parent_index.isValid():
            parent_index = self.index(0, 0, parent_index)

        parent_index = self._nearest_ngw_group_resource_parent(parent_index)

        parent_item = parent_index.internalPointer()
        ngw_resource_parent = parent_item.data(0, parent_item.NGWResourceRole)

        worker = CurrentQGISProjectImporter(ngw_group_name, ngw_resource_parent, iface)
        self._stratJobOnNGWResource(
            worker,
            self.JOB_IMPORT_QGIS_PROJECT,
            functools.partial(self.__importFinished, parent_index),
            parent_index
        )

    def __importFinished(self, parent_index):
        self._reloadChildren(parent_index)


class QGISResourceJob(NGWResourceModelJob):
    def __init__(self):
        NGWResourceModelJob.__init__(self)

    def importQGISMapLayer(self, qgs_map_layer, ngw_parent_resource):
        def export_to_json(qgs_vector_layer):
            tmp = tempfile.mktemp('.geojson')
            import_crs = QgsCoordinateReferenceSystem(4326, QgsCoordinateReferenceSystem.EpsgCrsId)
            # QgsMessageLog.logMessage("export_to_shapefile: %s" % qgs_vector_layer.crs().authid())
            # QgsMessageLog.logMessage("export_to_shapefile: %s" % import_crs.authid())
            QgsVectorFileWriter.writeAsVectorFormat(
                qgs_vector_layer,
                tmp,
                'utf-8',
                import_crs,
                'GeoJSON'
            )
            return tmp

        def export_to_shapefile(qgs_vector_layer):
            tmp = tempfile.mktemp('.shp')

            import_crs = QgsCoordinateReferenceSystem(4326, QgsCoordinateReferenceSystem.EpsgCrsId)
            QgsMessageLog.logMessage("export_to_shapefile: %s" % qgs_vector_layer.crs().authid())
            QgsMessageLog.logMessage("export_to_shapefile: %s" % import_crs.authid())
            QgsVectorFileWriter.writeAsVectorFormat(
                qgs_vector_layer,
                tmp,
                'utf-8',
                import_crs,
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

        layer_name = qgs_map_layer.name()
        chd_names = [ch.common.display_name for ch in ngw_parent_resource.get_children()]
        new_layer_name = self.generate_unique_name(layer_name, chd_names)

        layer_type = qgs_map_layer.type()
        QgsMessageLog.logMessage("export_to_shapefile layer_type: %d (%d)" % (layer_type, qgs_map_layer.VectorLayer))
        if layer_type == qgs_map_layer.VectorLayer:
            if qgs_map_layer.geometryType() in [QGis.NoGeometry, QGis.UnknownGeometry]:
                QgsMessageLog.logMessage("Vector layer '%s' has no geometry" % (layer_name, ))
                return None

            layer_provider = qgs_map_layer.providerType()
            # QgsMessageLog.logMessage("export_to_shapefile layer_provider: %s" % layer_provider)
            if layer_provider in ['ogr', 'memory']:
                QgsMessageLog.logMessage("Import layer %s (%s)" % (layer_name, layer_provider, ))
                # Import as shape ----
                # source = export_to_shapefile(qgs_map_layer)
                # QgsMessageLog.logMessage("export_to_shapefile source: %s" % source)
                # filepath = compress_shapefile(source)
                # QgsMessageLog.logMessage("export_to_shapefile filepath: %s" % filepath)

                # Import as GeoJSON ----
                filepath = export_to_json(qgs_map_layer)
                # QgsMessageLog.logMessage("export_to_shapefile filepath: %s" % filepath)

                ngw_vector_layer = ResourceCreator.create_vector_layer(
                    ngw_parent_resource,
                    filepath,
                    new_layer_name
                )

                # os.remove(source)
                os.remove(filepath)

                return ngw_vector_layer
        elif layer_type == QgsMapLayer.RasterLayer:
            layer_provider = qgs_map_layer.providerType()
            if layer_provider == 'gdal':
                filepath = qgs_map_layer.source()
                ngw_raster_layer = ResourceCreator.create_raster_layer(
                    ngw_parent_resource,
                    filepath,
                    new_layer_name
                )

                return ngw_raster_layer

        return None

    def addStyle(self, qgs_map_layer, ngw_layer_resource):
        layer_type = qgs_map_layer.type()
        if layer_type == QgsMapLayer.VectorLayer:
            tmp = tempfile.mktemp('.qml')
            msg, saved = qgs_map_layer.saveNamedStyle(tmp)

            ngw_resource = ResourceCreator.create_vector_layer_style(
                ngw_layer_resource,
                tmp,
                qgs_map_layer.name()
            )

            os.remove(tmp)
            return ngw_resource
        elif layer_type == QgsMapLayer.RasterLayer:
            layer_provider = qgs_map_layer.providerType()
            if layer_provider == 'gdal':
                ngw_resource = ResourceCreator.create_raster_layer_style(
                    ngw_layer_resource,
                    qgs_map_layer.name()
                )
                return ngw_resource

        return None


class QGISResourceImporter(QGISResourceJob):
    done = pyqtSignal(object)

    def __init__(self, qgs_map_layer, ngw_parent_resource):
        QGISResourceJob.__init__(self)
        self.qgs_map_layer = qgs_map_layer
        self.ngw_parent_resource = ngw_parent_resource

    def run(self):
        self.started.emit()

        try:
            ngw_resource = self.importQGISMapLayer(
                self.qgs_map_layer,
                self.ngw_parent_resource
            )

            self.addStyle(
                self.qgs_map_layer,
                ngw_resource
            )

            self.done.emit(ngw_resource)

        except NGWError as e:
            self.errorOccurred.emit(e.message)

        except Exception as e:
            self.errorOccurred.emit(str(e))

        self.finished.emit()


class CurrentQGISProjectImporter(QGISResourceJob):
    done = pyqtSignal()

    def __init__(self, new_group_name, ngw_resource_parent, iface):
        QGISResourceJob.__init__(self)
        self.new_group_name = new_group_name
        self.ngw_resource_parent = ngw_resource_parent
        self.iface = iface

    def run(self):
        self.started.emit()

        current_project = QgsProject.instance()

        try:
            chd_names = [ch.common.display_name for ch in self.ngw_resource_parent.get_children()]

            new_group_name = self.generate_unique_name(self.new_group_name, chd_names)

            ngw_group_resource = ResourceCreator.create_group(
                self.ngw_resource_parent,
                new_group_name
            )

            ngw_webmap_root_group = NGWWebMapRoot()

            def process_one_level_of_layers_tree(qgsLayerTreeItems, ngw_resource_group, ngw_webmap_item):
                for qgsLayerTreeItem in qgsLayerTreeItems:

                    if isinstance(qgsLayerTreeItem, QgsLayerTreeLayer):
                        self.statusChanged.emit("Import curent qgis project: layer %s" % qgsLayerTreeItem.layer().name())
                        QgsMessageLog.logMessage("Import curent qgis project: layer %s" % qgsLayerTreeItem.layer().name())
                        # progressDlg.setMessage(self.tr("Import layer %s") % qgsLayerTreeItem.layer().name())
                        ngw_layer_resource = self.importQGISMapLayer(
                            qgsLayerTreeItem.layer(),
                            ngw_resource_group
                        )

                        if ngw_layer_resource is None:
                            continue

                        ngw_style_resource = self.addStyle(
                            qgsLayerTreeItem.layer(),
                            ngw_layer_resource
                        )

                        if ngw_style_resource is None:
                            continue

                        ngw_webmap_item.appendChild(
                            NGWWebMapLayer(
                                ngw_style_resource.common.id,
                                qgsLayerTreeItem.layer().name(),
                                qgsLayerTreeItem.isVisible() == QtCore.Qt.Checked
                            )
                        )

                    if isinstance(qgsLayerTreeItem, QgsLayerTreeGroup):
                        chd_names = [ch.common.display_name for ch in ngw_resource_group.get_children()]

                        group_name = qgsLayerTreeItem.name()
                        self.statusChanged.emit("Import curent qgis project: folder %s" % group_name)

                        if group_name in chd_names:
                            id = 1
                            while(group_name + str(id) in chd_names):
                                id += 1
                            group_name += str(id)

                        ngw_resource_child_group = ResourceCreator.create_group(
                            ngw_resource_group,
                            group_name
                        )

                        ngw_webmap_child_group = NGWWebMapGroup(
                            group_name,
                            qgsLayerTreeItem.isExpanded()
                        )
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

            self.statusChanged.emit("Import curent qgis project: create webmap")
            self.add_webmap(
                ngw_group_resource,
                self.new_group_name + u"-webmap",
                ngw_webmap_root_group.children
            )

            self.done.emit()

        except NGWError as e:
            self.errorOccurred.emit(e.message)

        except Exception as e:
            self.errorOccurred.emit(str(e))

        self.finished.emit()

    def add_webmap(self, ngw_resource, ngw_webmap_name, ngw_webmap_items):
        rectangle = self.iface.mapCanvas().extent()
        ct = QgsCoordinateTransform(
            self.iface.mapCanvas().mapRenderer().destinationCrs(),
            QgsCoordinateReferenceSystem(4326, QgsCoordinateReferenceSystem.EpsgCrsId)
        )
        rectangle = ct.transform(rectangle)

        ngw_webmap_items_as_dicts = [item.toDict() for item in ngw_webmap_items]
        ngw_resource = ResourceCreator.create_webmap(
            ngw_resource,
            ngw_webmap_name,
            ngw_webmap_items_as_dicts,
            [
                rectangle.xMinimum(),
                rectangle.xMaximum(),
                rectangle.yMaximum(),
                rectangle.yMinimum(),
            ]
        )

        return ngw_resource
