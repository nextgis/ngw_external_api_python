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
import shutil
import zipfile
import tempfile

from PyQt4.QtCore import *

from qgis.core import *
from qgis.gui import *

from ..qt.qt_ngw_resource_base_model import *
from ..qt.qt_ngw_resource_edit_model import *
from ..qt.qt_ngw_resource_model_job import *

from ..core.ngw_webmap import NGWWebMapLayer, NGWWebMapGroup, NGWWebMapRoot
from ..core.ngw_resource_creator import ResourceCreator
from ..core.ngw_vector_layer import NGWVectorLayer
from ..core.ngw_qgis_vector_style import NGWQGISVectorStyle
from ..core.ngw_raster_layer import NGWRasterLayer

from ngw_plugin_settings import NgwPluginSettings


class QNGWResourcesModel4QGIS(QNGWResourcesModel):
    JOB_IMPORT_QGIS_RESOURCE = "IMPORT_QGIS_RESOURCE"
    JOB_IMPORT_QGIS_PROJECT = "IMPORT_QGIS_PROJECT"
    JOB_CREATE_NGW_STYLE = "CREATE_NGW_STYLE"
    JOB_CREATE_NGW_WMS_SERVICE = "CREATE_NGW_WMS_SERVICE"

    def __init__(self, parent):
        QNGWResourcesModel.__init__(self, parent)

    @modelRequest()
    def createNGWLayer(self, qgs_map_layers, parent_index):
        if not parent_index.isValid():
            parent_index = self.index(0, 0, parent_index)

        parent_index = self._nearest_ngw_group_resource_parent(parent_index)

        parent_item = parent_index.internalPointer()
        ngw_parent_resource = parent_item.data(0, Qt.UserRole)

        return self._startJob(
            QGISResourcesImporter(qgs_map_layers, ngw_parent_resource),
            self.JOB_IMPORT_QGIS_RESOURCE,
            self.processJobResult,
        )

    @modelRequest()
    def createOrUpdateQGISStyle(self, qgs_map_layer, index):
        if not index.isValid():
            index = self.index(0, 0, index)

        item = index.internalPointer()
        ngw_resource = item.data(0, Qt.UserRole)

        return self._startJob(
            QGISStyleImporter(qgs_map_layer, ngw_resource),
            self.JOB_IMPORT_QGIS_RESOURCE,
            self.processJobResult,
        )

    @modelRequest()
    def tryImportCurentQGISProject(self, ngw_group_name, parent_index, iface):
        if not parent_index.isValid():
            parent_index = self.index(0, 0, parent_index)

        parent_index = self._nearest_ngw_group_resource_parent(parent_index)

        parent_item = parent_index.internalPointer()
        ngw_resource_parent = parent_item.data(0, parent_item.NGWResourceRole)

        return self._startJob(
            CurrentQGISProjectImporter(ngw_group_name, ngw_resource_parent, iface),
            self.JOB_IMPORT_QGIS_PROJECT,
            self.processJobResult,
        )

    @modelRequest()
    def createMapForLayer(self, index, ngw_style_id):
        if not index.isValid():
            index = self.index(0, 0, index)

        item = index.internalPointer()
        ngw_resource = item.data(0, Qt.UserRole)

        return self._startJob(
            MapForLayerCreater(ngw_resource, ngw_style_id),
            self.JOB_CREATE_NGW_WEB_MAP,
            self.processJobResult,
        )

    @modelRequest()
    def createWMSForVector(self, index, ngw_resource_style_id):
        if not index.isValid():
            index = self.index(0, 0, index)

        parent_index = self._nearest_ngw_group_resource_parent(index)

        parent_item = parent_index.internalPointer()
        ngw_parent_resource = parent_item.data(0, Qt.UserRole)

        item = index.internalPointer()
        ngw_resource = item.data(0, Qt.UserRole)

        return self._startJob(
            NGWCreateWMSForVector(ngw_resource, ngw_parent_resource, ngw_resource_style_id),
            self.JOB_CREATE_NGW_WMS_SERVICE,
            self.processJobResult,
        )

class QGISResourceJob(NGWResourceModelJob):
    SUITABLE_LAYER = 0
    SUITABLE_LAYER_BAD_GEOMETRY = 1

    def __init__(self):
        NGWResourceModelJob.__init__(self)

        self.sanitize_fields_names = ["id", "type", "source"]

    def isSuitableLayer(self, qgs_map_layer):
        layer_type = qgs_map_layer.type()

        if layer_type == qgs_map_layer.VectorLayer:
            if qgs_map_layer.geometryType() in [QGis.NoGeometry, QGis.UnknownGeometry]:
                return self.SUITABLE_LAYER_BAD_GEOMETRY

        return self.SUITABLE_LAYER

    def importQGISMapLayer(self, qgs_map_layer, ngw_parent_resource):
        ngw_parent_resource.update()

        layer_name = qgs_map_layer.name()
        chd_names = [ch.common.display_name for ch in ngw_parent_resource.get_children()]
        new_layer_name = self.generate_unique_name(layer_name, chd_names)

        layer_type = qgs_map_layer.type()
        if layer_type == qgs_map_layer.VectorLayer:
            return self.importQgsVectorLayer(qgs_map_layer, ngw_parent_resource, new_layer_name)

        elif layer_type == QgsMapLayer.RasterLayer:
            return self.importQgsRasterLayer(qgs_map_layer, ngw_parent_resource, new_layer_name)

        return None

    def importQgsRasterLayer(self, qgs_raster_layer, ngw_parent_resource, new_layer_name):
        def uploadFileCallback(total_size, readed_size):
            self.statusChanged.emit(
                "%s - Upload (%d%%)" % (
                    qgs_raster_layer.name(),
                    readed_size * 100 / total_size
                )
            )
        layer_provider = qgs_raster_layer.providerType()
        if layer_provider == 'gdal':
            filepath = qgs_raster_layer.source()
            ngw_raster_layer = ResourceCreator.create_raster_layer(
                ngw_parent_resource,
                filepath,
                new_layer_name,
                uploadFileCallback
            )

            return ngw_raster_layer

    def importQgsVectorLayer(self, qgs_vector_layer, ngw_parent_resource, new_layer_name):
        def uploadFileCallback(total_size, readed_size):
            self.statusChanged.emit(
                "%s - Upload (%d%%)" % (
                    qgs_vector_layer.name(),
                    readed_size * 100 / total_size
                )
            )

        if self.isSuitableLayer(qgs_vector_layer) == self.SUITABLE_LAYER_BAD_GEOMETRY:
            self.errorOccurred.emit(
                QNGWResourcesModelExeption(
                    "Vector layer '%s' has no suitable geometry" % qgs_vector_layer.name()
                )
            )
            return None

        filepath, rename_fields_map = self.prepareImportFile(qgs_vector_layer)

        if filepath is None:
            self.errorOccurred.emit(
                QNGWResourcesModelExeption(
                    "Can't prepare layer'%s'. Skiped!" % qgs_vector_layer.name()
                )
            )
            return None

        ngw_vector_layer = ResourceCreator.create_vector_layer(
            ngw_parent_resource,
            filepath,
            new_layer_name,
            uploadFileCallback
        )

        aliases = {}
        src_layer_aliases = qgs_vector_layer.attributeAliases()
        for fn, rfn in rename_fields_map.items():
            if src_layer_aliases.has_key(fn):
               aliases[rfn] = src_layer_aliases[fn]

        if len(aliases) > 0:
            self.statusChanged.emit(
                "%s - Add aliases" % qgs_vector_layer.name()
            )
            ngw_vector_layer.add_aliases(aliases)

        self.statusChanged.emit(
            "%s - Finishing" % qgs_vector_layer.name()
        )

        os.remove(filepath)
        return ngw_vector_layer

    def prepareImportFile(self, qgs_vector_layer):
        self.statusChanged.emit(
            "%s - Prepare" % qgs_vector_layer.name()
        )

        layer_has_mixed_geoms = False
        layer_has_bad_fields = False
        if NgwPluginSettings.get_sanitize_fix_geometry():
            if self.hasSimpleAndMultyGeom(qgs_vector_layer):
                layer_has_mixed_geoms = True
        if NgwPluginSettings.get_sanitize_rename_fields():
            if self.hasBadFields(qgs_vector_layer):
                layer_has_bad_fields = True

        rename_fields_map = {}
        if layer_has_mixed_geoms or layer_has_bad_fields:
            layer, rename_fields_map = self.createLayer4Upload(qgs_vector_layer, layer_has_mixed_geoms, layer_has_bad_fields)
        else:
            layer = qgs_vector_layer

        import_format = u'ESRI Shapefile'
        if layer.featureCount() > 0:
            layer_provider = layer.dataProvider()
            if layer_provider.storageType() in [u'ESRI Shapefile']:
                import_format = layer_provider.storageType()
            else:
                import_format = u"GeoJSON"

        if import_format == u'ESRI Shapefile':
            return self.prepareAsShape(layer), rename_fields_map
        else:
            return self.prepareAsJSON(layer), rename_fields_map

    def hasSimpleAndMultyGeom(self, qgs_vector_layer):
        has_simple_geometries = False
        has_multipart_geometries = False

        features_count = qgs_vector_layer.featureCount()
        features_counter = 0
        progress = 0
        for feature in qgs_vector_layer.getFeatures():
            v = features_counter * 100 / features_count
            if progress < v:
                progress = v
                self.statusChanged.emit(
                    "%s - Check geometry (%d%%)" % (
                        qgs_vector_layer.name(),
                        features_counter * 100 / features_count
                    )
                )
            features_counter += 1
            if feature.geometry().isMultipart():
                has_multipart_geometries = True
            else:
                has_simple_geometries = True

            if has_multipart_geometries and has_simple_geometries:
                break

        self.statusChanged.emit(
            "%s - Check geometry (%d%%)" % (
                qgs_vector_layer.name(),
                100
            )
        )
        return has_multipart_geometries and has_simple_geometries

    def hasBadFields(self, qgs_vector_layer):
        exist_fields_names = [field.name().lower() for field in qgs_vector_layer.fields()]
        common_fields = list(set(exist_fields_names).intersection(self.sanitize_fields_names))

        return len(common_fields) > 0

    def createLayer4Upload(self, qgs_vector_layer_src, has_mixed_geoms, has_bad_fields):
        geometry_type = self.determineGeometry4MemoryLayer(qgs_vector_layer_src, has_mixed_geoms)

        field_name_map = {}
        if has_bad_fields:
            field_name_map = self.getFieldsForRename(qgs_vector_layer_src)

            if len(field_name_map) != 0:
                msg = QCoreApplication.translate(
                    "QGISResourceJob",
                    "We've renamed fields {0} for layer '{1}'. Style for this layer may become invalid."
                ).format(
                    field_name_map.keys(),
                    qgs_vector_layer_src.name()
                )

                self.warningOccurred.emit(
                    QNGWResourcesModelExeption(msg)
                )

        qgs_vector_layer_dst = QgsVectorLayer(
            "%s?crs=epsg:4326" % geometry_type,
            "temp",
            "memory"
        )

        qgs_vector_layer_dst.startEditing()

        for field in qgs_vector_layer_src.fields():
            field.setName(
                field_name_map.get(field.name(), field.name())
            )
            qgs_vector_layer_dst.addAttribute(field)

        qgs_vector_layer_dst.commitChanges()
        qgs_vector_layer_dst.startEditing()
        features_count = qgs_vector_layer_src.featureCount()
        features_counter = 1
        for feature in qgs_vector_layer_src.getFeatures():
            if has_mixed_geoms:
                new_geometry = feature.geometry()
                new_geometry.convertToMultiType()
                feature.setGeometry(
                    new_geometry
                )
            qgs_vector_layer_dst.addFeature(feature)

            self.statusChanged.emit(
                "%s - Prepare layer for import (%d%%)" % (
                    qgs_vector_layer_src.name(),
                    features_counter * 100 / features_count
                )
            )
            features_counter += 1

        qgs_vector_layer_dst.commitChanges()

        return qgs_vector_layer_dst, field_name_map

    def determineGeometry4MemoryLayer(self, qgs_vector_layer, has_mixed_geoms):
        geometry_type = None
        if qgs_vector_layer.geometryType() == QGis.Point:
            geometry_type = "point"
        elif qgs_vector_layer.geometryType() == QGis.Line:
            geometry_type = "linestring"
        elif qgs_vector_layer.geometryType() == QGis.Polygon:
            geometry_type = "polygon"

        # if has_multipart_geometries:
        if has_mixed_geoms:
            geometry_type = "multi" + geometry_type

        return geometry_type

    def getFieldsForRename(self, qgs_vector_layer):
        field_name_map = {}

        exist_fields_names = [field.name() for field in qgs_vector_layer.fields()]
        for field in qgs_vector_layer.fields():
            if field.name().lower() in self.sanitize_fields_names:
                new_field_name = field.name()
                suffix = 1
                while new_field_name in exist_fields_names:
                    new_field_name = field.name() + str(suffix)
                    suffix += 1
                field_name_map.update({field.name(): new_field_name})

        return field_name_map

    def prepareAsShape(self, qgs_vector_layer):
        tmp_dir = tempfile.mkdtemp('ngw_api_prepare_import')
        tmp_shp = os.path.join(tmp_dir, '4import.shp')

        import_crs = QgsCoordinateReferenceSystem(4326, QgsCoordinateReferenceSystem.EpsgCrsId)
        QgsVectorFileWriter.writeAsVectorFormat(
            qgs_vector_layer,
            tmp_shp,
            'utf-8',
            import_crs,
        )

        tmp = tempfile.mktemp('.zip')
        basePath = os.path.splitext(tmp_shp)[0]
        baseName = os.path.splitext(os.path.basename(tmp_shp))[0]

        self.statusChanged.emit(
            "%s - Packing" % qgs_vector_layer.name()
        )

        zf = zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED)
        for i in glob.iglob(basePath + '.*'):
            ext = os.path.splitext(i)[1]
            zf.write(i, baseName + ext)

        zf.close()
        shutil.rmtree(tmp_dir)

        return tmp

    def prepareAsJSON(self, qgs_vector_layer):
        tmp = tempfile.mktemp('.geojson')
        import_crs = QgsCoordinateReferenceSystem(4326, QgsCoordinateReferenceSystem.EpsgCrsId)
        QgsVectorFileWriter.writeAsVectorFormat(
            qgs_vector_layer,
            tmp,
            'utf-8',
            import_crs,
            'GeoJSON'
        )

        return tmp

    def addQMLStyle(self, qml, ngw_layer_resource):
        def uploadFileCallback(total_size, readed_size):
            self.statusChanged.emit(
                "Style for %s - Upload (%d%%)" % (
                    ngw_layer_resource.common.display_name,
                    readed_size * 100 / total_size
                )
            )

        ngw_style = ngw_layer_resource.create_qml_style(
            qml,
            uploadFileCallback
        )
        return ngw_style

    def addStyle(self, qgs_map_layer, ngw_layer_resource):
        layer_type = qgs_map_layer.type()
        if layer_type == QgsMapLayer.VectorLayer:
            tmp = tempfile.mktemp('.qml')
            self.statusChanged.emit(
                "Style for %s - Save as qml" % qgs_map_layer.name()
            )
            msg, saved = qgs_map_layer.saveNamedStyle(tmp)
            ngw_resource = self.addQMLStyle(tmp, ngw_layer_resource)
            os.remove(tmp)
            return ngw_resource
        elif layer_type == QgsMapLayer.RasterLayer:
            layer_provider = qgs_map_layer.providerType()
            if layer_provider == 'gdal':
                ngw_resource = ngw_layer_resource.create_style()
                return ngw_resource

        return None

    def updateQMLStyle(self, qml, ngw_qgis_vector_resource):
        def uploadFileCallback(total_size, readed_size):
            self.statusChanged.emit(
                "Style for %s - Upload (%d%%)" % (
                    ngw_qgis_vector_resource.common.display_name,
                    readed_size * 100 / total_size
                )
            )

        ngw_qgis_vector_resource.update_qml(
            qml,
            uploadFileCallback
        )

    def updateStyle(self, qgs_map_layer, ngw_qgis_vector_resource):
        layer_type = qgs_map_layer.type()
        if layer_type == QgsMapLayer.VectorLayer:
            tmp = tempfile.mktemp('.qml')
            self.statusChanged.emit(
                "Style for %s - Save as qml" % qgs_map_layer.name()
            )
            msg, saved = qgs_map_layer.saveNamedStyle(tmp)
            self.updateQMLStyle(tmp, ngw_qgis_vector_resource)
            os.remove(tmp)

    def getQMLDefaultStyle(self):
        gtype = self.ngw_layer._json[self.ngw_layer.type_id]["geometry_type"]

        if gtype in ["LINESTRING", "MULTILINESTRING"]:
            return os.path.join(
                os.path.dirname(__file__),
                "line_style.qml"
            )
        if gtype in ["POINT", "MULTIPOINT"]:
            return os.path.join(
                os.path.dirname(__file__),
                "point_style.qml"
            )
        if gtype in ["POLYGON", "MULTIPOLYGON"]:
            return os.path.join(
                os.path.dirname(__file__),
                "polygon_style.qml"
            )

        return None

    def _defStyleForVector(self, ngw_layer):
        qml = self.getQMLDefaultStyle()

        if qml is None:
            self.errorOccurred.emit("There is no defalut style description for create new style.")
            return

        ngw_style = self.addQMLStyle(qml, ngw_layer)

        return ngw_style

    def _defStyleForRaster(self, ngw_layer):
        ngw_style = ngw_layer.create_style()
        return ngw_style

class QGISResourcesImporter(QGISResourceJob):
    def __init__(self, qgs_map_layers, ngw_parent_resource):
        QGISResourceJob.__init__(self)
        self.qgs_map_layers = qgs_map_layers
        self.ngw_parent_resource = ngw_parent_resource

    def _do(self):
        for qgs_map_layer in self.qgs_map_layers:
            ngw_resource = self.importQGISMapLayer(
                qgs_map_layer,
                self.ngw_parent_resource
            )
            # QgsMessageLog.logMessage("QGISResourceImporter ngw_resource: %d" % ngw_resource.common.id)
            if ngw_resource is None:
                return

            # QgsMessageLog.logMessage("QGISResourceImporter add style start")
            ngw_style = self.addStyle(
            qgs_map_layer,
                ngw_resource
            )
            # QgsMessageLog.logMessage("QGISResourceImporter added style: %d" % ngw_style.common.id)

            result = NGWResourceModelJobResult()
            result.putAddedResource(ngw_resource, is_main=True)
            result.putAddedResource(ngw_style)

            self.dataReceived.emit(result)


class CurrentQGISProjectImporter(QGISResourceJob):
    def __init__(self, new_group_name, ngw_resource_parent, iface):
        QGISResourceJob.__init__(self)
        self.new_group_name = new_group_name
        self.ngw_resource_parent = ngw_resource_parent
        self.iface = iface

    def _do(self):
        current_project = QgsProject.instance()
        result = NGWResourceModelJobResult()

        new_group_name = self.unique_resource_name(self.new_group_name, self.ngw_resource_parent)

        ngw_group_resource = ResourceCreator.create_group(
            self.ngw_resource_parent,
            new_group_name
        )

        result.putAddedResource(ngw_group_resource)

        ngw_webmap_root_group = NGWWebMapRoot()

        skip_import_layer_error = NgwPluginSettings.get_force_qgis_project_import()

        def process_one_level_of_layers_tree(qgsLayerTreeItems, ngw_resource_group, ngw_webmap_item):
            for qgsLayerTreeItem in qgsLayerTreeItems:

                if isinstance(qgsLayerTreeItem, QgsLayerTreeLayer):
                    if self.isSuitableLayer(qgsLayerTreeItem.layer()) != self.SUITABLE_LAYER:
                        continue

                    try:
                        ngw_layer_resource = self.importQGISMapLayer(
                            qgsLayerTreeItem.layer(),
                            ngw_resource_group
                        )
                    except Exception as e:
                        exception = QNGWResourcesModelExeption(
                            self.tr("Import '%s'" % qgsLayerTreeItem.layer().name()),
                            e
                        )
                        if skip_import_layer_error:
                            self.warningOccurred.emit(
                                exception
                            )
                            continue
                        else:
                            raise exception

                    if ngw_layer_resource is None:
                        continue

                    result.putAddedResource(ngw_layer_resource)

                    ngw_style_resource = self.addStyle(
                        qgsLayerTreeItem.layer(),
                        ngw_layer_resource
                    )

                    if ngw_style_resource is None:
                        continue

                    result.putAddedResource(ngw_style_resource)

                    ngw_webmap_item.appendChild(
                        NGWWebMapLayer(
                            ngw_style_resource.common.id,
                            qgsLayerTreeItem.layer().name(),
                            qgsLayerTreeItem.isVisible() == Qt.Checked
                        )
                    )

                if isinstance(qgsLayerTreeItem, QgsLayerTreeGroup):
                    chd_names = [ch.common.display_name for ch in ngw_resource_group.get_children()]

                    group_name = qgsLayerTreeItem.name()
                    self.statusChanged.emit("Import folder %s" % group_name)

                    if group_name in chd_names:
                        id = 1
                        while(group_name + str(id) in chd_names):
                            id += 1
                        group_name += str(id)

                    ngw_resource_child_group = ResourceCreator.create_group(
                        ngw_resource_group,
                        group_name
                    )
                    result.putAddedResource(ngw_resource_child_group)

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
        ngw_webmap = self.add_webmap(
            ngw_group_resource,
            self.new_group_name + u"-webmap",
            ngw_webmap_root_group.children
        )
        result.putAddedResource(ngw_webmap, is_main=True)

        self.dataReceived.emit(result)

    def add_webmap(self, ngw_resource, ngw_webmap_name, ngw_webmap_items):
        rectangle = self.iface.mapCanvas().extent()
        ct = QgsCoordinateTransform(
            self.iface.mapCanvas().mapSettings().destinationCrs(),
            QgsCoordinateReferenceSystem(4326, QgsCoordinateReferenceSystem.EpsgCrsId)
        )

        bbox = ct.transform(QgsRectangle(-179.9, -89.9, 179.9, 89.9), QgsCoordinateTransform.ReverseTransform)
        rectangle = rectangle.intersect(bbox)

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


class MapForLayerCreater(QGISResourceJob):
    def __init__(self, ngw_layer, ngw_style_id):
        NGWResourceModelJob.__init__(self)
        self.ngw_layer = ngw_layer
        self.ngw_style_id = ngw_style_id

    def _do(self):
        result = NGWResourceModelJobResult()

        if self.ngw_style_id is None:
            if self.ngw_layer.type_id == NGWVectorLayer.type_id:
                ngw_style = self._defStyleForVector(self.ngw_layer)
                result.putAddedResource(ngw_style)
                self.ngw_style_id = ngw_style.common.id

            if self.ngw_layer.type_id == NGWRasterLayer.type_id:
                ngw_style = self._defStyleForRaster(self.ngw_layer)
                result.putAddedResource(ngw_style)
                self.ngw_style_id = ngw_style.common.id

        ngw_webmap_root_group = NGWWebMapRoot()
        ngw_webmap_root_group.appendChild(
            NGWWebMapLayer(
                self.ngw_style_id,
                self.ngw_layer.common.display_name,
                True
            )
        )

        ngw_group = self.ngw_layer.get_parent()

        ngw_map_name = self.unique_resource_name(
            self.ngw_layer.common.display_name + "-map",
            ngw_group
        )

        ngw_resource = ResourceCreator.create_webmap(
            ngw_group,
            ngw_map_name,
            [item.toDict() for item in ngw_webmap_root_group.children],
            bbox=self.ngw_layer.extent()
        )

        result.putAddedResource(ngw_resource, is_main=True)

        self.dataReceived.emit(result)


class QGISStyleImporter(QGISResourceJob):
    def __init__(self, qgs_map_layer, ngw_resource):
        QGISResourceJob.__init__(self)
        self.qgs_map_layer = qgs_map_layer
        self.ngw_resource = ngw_resource

    def _do(self):
        result = NGWResourceModelJobResult()

        if self.ngw_resource.type_id == NGWVectorLayer.type_id:
            ngw_style = self.addStyle(self.qgs_map_layer, self.ngw_resource)
            result.putAddedResource(ngw_style)
        elif self.ngw_resource.type_id == NGWQGISVectorStyle.type_id:
            self.updateStyle(self.qgs_map_layer, self.ngw_resource)
            result.putEditedResource(self.ngw_resource)

        self.dataReceived.emit(result)


class NGWCreateWMSForVector(QGISResourceJob):
    def __init__(self, ngw_vector_layer, ngw_group_resource, ngw_style_id):
        NGWResourceModelJob.__init__(self)
        self.ngw_layer = ngw_vector_layer
        self.ngw_group_resource = ngw_group_resource
        self.ngw_style_id = ngw_style_id

    def _do(self):
        result = NGWResourceModelJobResult()

        if self.ngw_style_id is None:
            if self.ngw_layer.type_id == NGWVectorLayer.type_id:
                ngw_style = self._defStyleForVector(self.ngw_layer)
                result.putAddedResource(ngw_style)
                self.ngw_style_id = ngw_style.common.id

            if self.ngw_layer.type_id == NGWRasterLayer.type_id:
                ngw_style = self._defStyleForRaster(self.ngw_layer)
                result.putAddedResource(ngw_style)
                self.ngw_style_id = ngw_style.common.id

        ngw_wms_service_name = self.unique_resource_name(
            self.ngw_layer.common.display_name + "-wms-service",
            self.ngw_group_resource)

        ngw_wfs_resource = NGWWmsService.create_in_group(
            ngw_wms_service_name,
            self.ngw_group_resource,
            [(self.ngw_layer, self.ngw_style_id)],
        )

        result.putAddedResource(ngw_wfs_resource, is_main=True)

        self.dataReceived.emit(result)