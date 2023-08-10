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
import pkg_resources
from typing import Optional

from qgis.PyQt.QtCore import QCoreApplication

from qgis.core import (
    QgsProject, QgsMapLayer, QgsVectorLayer, QgsFeature,
    QgsLayerTreeLayer, QgsLayerTreeGroup, QgsVectorFileWriter,
    QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsProviderRegistry,
)
from qgis.gui import QgsFileWidget

from ..qt.qt_ngw_resource_model_job import *
from ..qt.qt_ngw_resource_model_job_error import *

from ..core.ngw_webmap import NGWWebMapLayer, NGWWebMapGroup, NGWWebMapRoot
from ..core.ngw_resource_creator import ResourceCreator
from ..core.ngw_vector_layer import NGWVectorLayer
from ..core.ngw_qgis_style import NGWQGISStyle, NGWQGISVectorStyle, NGWQGISRasterStyle
from ..core.ngw_feature import NGWFeature
from ..core.ngw_raster_layer import NGWRasterLayer
from ..core.ngw_wms_service import NGWWmsService
from ..core.ngw_wms_connection import NGWWmsConnection
from ..core.ngw_wms_layer import NGWWmsLayer
from ..core.ngw_webmap import NGWWebMap
from ..core.ngw_base_map import NGWBaseMap, NGWBaseMapExtSettings
from ..utils import log

from ..utils import ngw_version_compare

from .ngw_plugin_settings import NgwPluginSettings

from .compat_qgis import QgsWkbTypes
from .compat_qgis import CompatQgis
from .compat_qgis import CompatQt
from .compat_qgis import CompatQgisGeometryType, CompatQgisWkbType


NGW_AUTORENAME_FIELDS_VERS = '4.1.0.dev5'


def getQgsMapLayerEPSG(qgs_map_layer):
    crs = qgs_map_layer.crs().authid()
    if crs.find("EPSG:") >= 0:
        return int(crs.split(":")[1])
    return None


def yOriginTopFromQgisTmsUrl(qgs_tms_url):
    return qgs_tms_url.find("{-y}")


def get_wkt(qgis_geometry):
    wkt = CompatQgis.wkt_geometry(qgis_geometry)

    #if qgis_geometry.wkbType() < 0: # TODO: why this check was made?
    wkb_type = CompatQgis.get_wkb_type(qgis_geometry.wkbType())
    wkt_fixes = {
        CompatQgisWkbType.WKBPoint25D: ('PointZ', 'Point Z'),
        CompatQgisWkbType.WKBLineString25D: ('LineStringZ', 'LineString Z'),
        CompatQgisWkbType.WKBPolygon25D: ('PolygonZ', 'Polygon Z'),
        CompatQgisWkbType.WKBMultiPoint25D: ('MultiPointZ', 'MultiPoint Z'),
        CompatQgisWkbType.WKBMultiLineString25D: ('MultiLineStringZ', 'MultiLineString Z'),
        CompatQgisWkbType.WKBMultiPolygon25D: ('MultiPolygonZ', 'MultiPolygon Z'),
    }

    if wkb_type in wkt_fixes:
        wkt = wkt.replace(*wkt_fixes[wkb_type])

    return wkt


class QGISResourceJob(NGWResourceModelJob):
    SUITABLE_LAYER = 0
    SUITABLE_LAYER_BAD_GEOMETRY = 1

    def __init__(self, ngw_version=None):
        super().__init__()

        self.ngw_version = ngw_version

        self.sanitize_fields_names = ["id", "geom"]

    def _layer_status(self, layer_name, status):
        self.statusChanged.emit(f""""{layer_name}" - {status}""")

    def isSuitableLayer(self, qgs_map_layer):
        layer_type = qgs_map_layer.type()

        if layer_type == qgs_map_layer.VectorLayer:
            if qgs_map_layer.geometryType() in [CompatQgisGeometryType.NoGeometry, CompatQgisGeometryType.UnknownGeometry]:
                return self.SUITABLE_LAYER_BAD_GEOMETRY

        return self.SUITABLE_LAYER

    def importQGISMapLayer(self, qgs_map_layer, ngw_parent_resource):
        ngw_parent_resource.update()

        layer_type = qgs_map_layer.type()

        if layer_type == qgs_map_layer.VectorLayer:
            return [self.importQgsVectorLayer(qgs_map_layer, ngw_parent_resource)]

        elif layer_type == QgsMapLayer.RasterLayer:
            layer_data_provider = qgs_map_layer.dataProvider().name()
            if layer_data_provider == "gdal":
                return [self.importQgsRasterLayer(qgs_map_layer, ngw_parent_resource)]

            elif layer_data_provider == "wms":
                return self.importQgsWMSLayer(qgs_map_layer, ngw_parent_resource)

        elif layer_type == QgsMapLayer.PluginLayer:
            return self.importQgsPluginLayer(qgs_map_layer, ngw_parent_resource)

        return []

    def baseMapCreationAvailabilityCheck(self, ngw_connection):
        abilities = ngw_connection.get_abilities()
        return ngw_connection.AbilityBaseMap in abilities

    def importQgsPluginLayer(self, qgs_plugin_layer, ngw_group):
        # Look for QMS plugin layer
        if qgs_plugin_layer.pluginLayerType() == 'PyTiledLayer' and hasattr(qgs_plugin_layer, "layerDef") and hasattr(qgs_plugin_layer.layerDef, "serviceUrl"):
            #log(u'>>> Uploading plugin layer "{}"'.format(qgs_plugin_layer.name()))

            # if not self.baseMapCreationAvailabilityCheck(ngw_group._res_factory.connection):
            #     raise JobError(self.tr("Your web GIS can't create base maps."))

            new_layer_name = self.unique_resource_name(qgs_plugin_layer.name(), ngw_group)

            epsg = getattr(qgs_plugin_layer.layerDef, "epsg_crs_id", None)
            if epsg is None:
                epsg = getQgsMapLayerEPSG(qgs_plugin_layer)

            basemap_ext_settings = NGWBaseMapExtSettings(
                getattr(qgs_plugin_layer.layerDef, "serviceUrl", None),
                epsg,
                getattr(qgs_plugin_layer.layerDef, "zmin", None),
                getattr(qgs_plugin_layer.layerDef, "zmax", None),
                getattr(qgs_plugin_layer.layerDef, "yOriginTop", None)
            )

            ngw_basemap = NGWBaseMap.create_in_group(new_layer_name, ngw_group, qgs_plugin_layer.layerDef.serviceUrl, basemap_ext_settings)

            return [ngw_basemap]

    def importQgsWMSLayer(self, qgs_wms_layer, ngw_group):
        # log(u'>>> Uploading WMS layer "{}"'.format(qgs_wms_layer.name()))

        self._layer_status(qgs_wms_layer.name(), self.tr("create WMS connection"))

        layer_source = qgs_wms_layer.source()
        provider_metadata = QgsProviderRegistry.instance().providerMetadata('wms')
        parameters = provider_metadata.decodeUri(layer_source)

        if parameters.get("type", "") == "xyz":

            # if not self.baseMapCreationAvailabilityCheck(ngw_group._res_factory.connection):
            #     raise JobError(self.tr("Your web GIS can't create base maps."))

            epsg = getQgsMapLayerEPSG(qgs_wms_layer)

            basemap_ext_settings = NGWBaseMapExtSettings(
                parameters.get("url"),
                epsg,
                parameters.get("zmin"),
                parameters.get("zmax"),
                yOriginTopFromQgisTmsUrl(parameters.get("url", ""))
            )

            ngw_basemap_name = self.unique_resource_name(qgs_wms_layer.name(), ngw_group)
            ngw_basemap = NGWBaseMap.create_in_group(ngw_basemap_name, ngw_group, parameters.get("url", ""), basemap_ext_settings)
            return [ngw_basemap]
        else:
            ngw_wms_connection_name = self.unique_resource_name(qgs_wms_layer.name(), ngw_group)
            wms_connection = NGWWmsConnection.create_in_group(
                ngw_wms_connection_name,
                ngw_group,
                parameters.get("url", ""),
                parameters.get("version", "1.1.1"),
                (parameters.get("username"), parameters.get("password"))
            )

            self._layer_status(qgs_wms_layer.name(), self.tr("creating WMS layer"))

            ngw_wms_layer_name = self.unique_resource_name(
                wms_connection.common.display_name + "_layer",
                ngw_group
            )

            layer_ids = parameters.get("layers", wms_connection.layers())
            if not isinstance(layer_ids, list):
                layer_ids = [layer_ids]

            wms_layer = NGWWmsLayer.create_in_group(
                ngw_wms_layer_name,
                ngw_group,
                wms_connection.common.id,
                layer_ids,
                parameters.get("format"),
            )
            return [wms_connection, wms_layer]

    def importQgsRasterLayer(self, qgs_raster_layer, ngw_parent_resource):
        new_layer_name = self.unique_resource_name(qgs_raster_layer.name(), ngw_parent_resource)
        log(u'>>> Uploading raster layer "{}" (with the name "{}")'.format(qgs_raster_layer.name(), new_layer_name))

        def uploadFileCallback(total_size, readed_size, value=None):
            if value is None:
                value = round(readed_size * 100 / total_size)
            self._layer_status(
                qgs_raster_layer.name(),
                self.tr("uploading ({}%)").format(value)
            )

        def createLayerCallback():
            self._layer_status(qgs_raster_layer.name(), self.tr("creating"))

        layer_provider = qgs_raster_layer.providerType()
        if layer_provider == 'gdal':
            filepath = qgs_raster_layer.source()
            ngw_raster_layer = ResourceCreator.create_raster_layer(
                ngw_parent_resource,
                filepath,
                new_layer_name,
                NgwPluginSettings.get_upload_cog_rasters(),
                uploadFileCallback,
                createLayerCallback
            )

            return ngw_raster_layer

    def importQgsVectorLayer(self, qgs_vector_layer, ngw_parent_resource):
        new_layer_name = self.unique_resource_name(qgs_vector_layer.name(), ngw_parent_resource)
        log(u'>>> Uploading vector layer "{}" (with the name "{}")'.format(qgs_vector_layer.name(), new_layer_name))

        def uploadFileCallback(total_size, readed_size, value=None):
            self._layer_status(
                qgs_vector_layer.name(),
                self.tr("uploading ({}%)").format(
                    int(readed_size * 100 / total_size if value is None else value)))

        def createLayerCallback():
            self._layer_status(qgs_vector_layer.name(), self.tr("creating"))

        if self.isSuitableLayer(qgs_vector_layer) == self.SUITABLE_LAYER_BAD_GEOMETRY:
            self.errorOccurred.emit(
                JobError(
                    "Vector layer '%s' has no suitable geometry" % qgs_vector_layer.name()
                )
            )
            return None

        filepath, tgt_qgs_layer, rename_fields_map = self.prepareImportFile(qgs_vector_layer)
        if filepath is None:
            self.errorOccurred.emit(
                JobError(
                    "Can't prepare layer '%s'. Skipped!" % qgs_vector_layer.name()
                )
            )
            return None

        ngw_geom_info = self._get_ngw_geom_info(tgt_qgs_layer)
        ngw_vector_layer = ResourceCreator.create_vector_layer(
            ngw_parent_resource,
            filepath,
            new_layer_name,
            uploadFileCallback,
            createLayerCallback,
            ngw_geom_info[0],
            ngw_geom_info[1],
            ngw_geom_info[2]
        )

        aliases = {}
        src_layer_aliases = qgs_vector_layer.attributeAliases()
        for fieldname, alias in list(src_layer_aliases.items()):
            # Check alias. This check is for QGIS 3: attributeAliases() returns dict where all
            # values are ''. In QGIS 2 it returns void dict so this loop is skipped.
            # We should avoid void aliases due to NGW limitations (NGW returns 422 error).
            if alias == '':
                continue
            if fieldname in rename_fields_map:
                aliases[rename_fields_map[fieldname]] = alias
            else:
                aliases[fieldname] = alias
        # for fn, rfn in rename_fields_map.items():
        #     if src_layer_aliases.has_key(fn):
        #        aliases[rfn] = src_layer_aliases[fn]

        if len(aliases) > 0:
            self._layer_status(qgs_vector_layer.name(), self.tr("adding aliases"))
            ngw_vector_layer.add_aliases(aliases)

        self._layer_status(qgs_vector_layer.name(), self.tr("finishing"))
        os.remove(filepath)

        return ngw_vector_layer


    def prepareImportFile(self, qgs_vector_layer):
        self._layer_status(qgs_vector_layer.name(), self.tr("preparing"))

        layer_has_mixed_geoms = False
        layer_has_bad_fields = False
        fids_with_notvalid_geom = []

        # Do not check geometries (rely on NGW):
        #if NgwPluginSettings.get_sanitize_fix_geometry():
        #    layer_has_mixed_geoms, fids_with_notvalid_geom = self.checkGeometry(qgs_vector_layer)

        # Check specific fields.
        if NgwPluginSettings.get_sanitize_rename_fields() and self.hasBadFields(qgs_vector_layer) and not self.ngwSupportsAutoRenameFields():
            log('Incorrect fields of layer will be renamed by NextGIS Connect')
            layer_has_bad_fields = True
        else:
            log('Incorrect fields of layer will NOT be renamed by NextGIS Connect')

        rename_fields_map = {}
        if layer_has_mixed_geoms or layer_has_bad_fields or (len(fids_with_notvalid_geom) > 0):
            layer, rename_fields_map = self.createLayer4Upload(qgs_vector_layer, fids_with_notvalid_geom, layer_has_mixed_geoms, layer_has_bad_fields)
        else:
            layer = qgs_vector_layer

        return self.prepareAsGPKG(layer), layer, rename_fields_map

    def checkGeometry(self, qgs_vector_layer):
        has_simple_geometries = False
        has_multipart_geometries = False

        fids_with_not_valid_geom = []

        features_count = qgs_vector_layer.featureCount()
        progress = 0
        for features_counter, feature in enumerate(qgs_vector_layer.getFeatures(), start=1):
            v = round(features_counter * 100 / features_count)
            if progress < v:
                progress = v
                self._layer_status(
                    qgs_vector_layer.name(),
                    self.tr("checking geometry ({}%)").format(progress))

            fid, geom = feature.geometry(), feature.id()

            if geom is None:
                fids_with_not_valid_geom.append(fid)
                continue

            # Fix one point line. Method isGeosValid return true for same geometry.
            if geom.type() == CompatQgisGeometryType.Line:
                if geom.isMultipart():
                    for polyline in geom.asMultiPolyline():
                        if len(polyline) < 2:
                            fids_with_not_valid_geom.append(fid)
                            break
                else:
                    if len(geom.asPolyline()) < 2:
                        fids_with_not_valid_geom.append(fid)

            elif geom.type() == CompatQgisGeometryType.Polygon:
                if geom.isMultipart():
                    for polygon in geom.asMultiPolygon():
                        for polyline in polygon:
                            if len(polyline) < 4:
                                log("Feature %s has not valid geometry (less then 4 points)" % str(fid))
                                fids_with_not_valid_geom.append(fid)
                                break
                else:
                    for polyline in geom.asPolygon():
                        if len(polyline) < 4:
                            log("Feature %s has not valid geometry (less then 4 points)" % str(fid))
                            fids_with_not_valid_geom.append(fid)
                            break

            if geom.isMultipart():
                has_multipart_geometries = True
            else:
                has_simple_geometries = True

            # Do not validate geometries (rely on NGW):
            # errors = feature.geometry().validateGeometry()
            # if len(errors) != 0:
            #     log("Feature %s has invalid geometry: %s" % (str(feature.id()), ', '.join(err.what() for err in errors)))
            #     fids_with_not_valid_geom.append(feature.id())

        return (
            has_multipart_geometries and has_simple_geometries,
            fids_with_not_valid_geom
        )

    def hasBadFields(self, qgs_vector_layer):
        exist_fields_names = [field.name().lower() for field in qgs_vector_layer.fields()]
        common_fields = list(set(exist_fields_names).intersection(self.sanitize_fields_names))

        return len(common_fields) > 0

    def ngwSupportsAutoRenameFields(self):
        if self.ngw_version is None:
            return False

        if CompatQgis.is_qgis_2():
            # A simple comparing, does not include all PEP440 checks.
            vers_ok = ngw_version_compare(self.ngw_version, NGW_AUTORENAME_FIELDS_VERS)
            if vers_ok == 1 or vers_ok == 0:
                vers_ok = True
            elif vers_ok == -1:
                vers_ok = False
        else:
            # A full PEP 440 comparing.
            current_ngw_version = pkg_resources.parse_version(self.ngw_version)
            ngw_version_with_support = pkg_resources.parse_version(
                NGW_AUTORENAME_FIELDS_VERS
            )
            vers_ok = current_ngw_version >= ngw_version_with_support

        if vers_ok:
            log('Assume that NGW of version "{}" supports auto-renaming fields'.format(self.ngw_version))
            return True
        log('Assume that NGW of version "{}" does NOT support auto-renaming fields'.format(self.ngw_version))

        return False

    def createLayer4Upload(self, qgs_vector_layer_src, fids_with_notvalid_geom, has_mixed_geoms, has_bad_fields):
        geometry_type = self.determineGeometry4MemoryLayer(qgs_vector_layer_src, has_mixed_geoms)

        field_name_map = {}
        if has_bad_fields:
            field_name_map = self.getFieldsForRename(qgs_vector_layer_src)

            if len(field_name_map) != 0:
                msg = QCoreApplication.translate(
                    "QGISResourceJob",
                    "We've renamed fields {0} for layer '{1}'. Style for this layer may become invalid."
                ).format(
                    list(field_name_map.keys()),
                    qgs_vector_layer_src.name()
                )

                self.warningOccurred.emit(
                    JobWarning(msg)
                )

        import_crs = QgsCoordinateReferenceSystem(4326, QgsCoordinateReferenceSystem.EpsgCrsId)
        qgs_vector_layer_dst = QgsVectorLayer(
            "%s?crs=%s" % (geometry_type, import_crs.authid()),
            "temp",
            "memory"
        )

        qgs_vector_layer_dst.startEditing()

        for field in qgs_vector_layer_src.fields():
            field.setName( # TODO: does it work? At least qgs_vector_layer_src is not in edit mode now. Also we obviously don't want to change source layer names here
                field_name_map.get(field.name(), field.name())
            )
            qgs_vector_layer_dst.addAttribute(field)

        qgs_vector_layer_dst.commitChanges()
        qgs_vector_layer_dst.startEditing()
        features_count = qgs_vector_layer_src.featureCount()

        progress = 0
        for features_counter, feature in enumerate(qgs_vector_layer_src.getFeatures(), start=1):
            if feature.id() in fids_with_notvalid_geom:
                continue

            # Additional checks for geom correctness.
            # TODO: this was done in self.checkGeometry() but we've remove using of this method. Maybe return using this method back.
            if CompatQgis.is_geom_empty(feature.geometry()):
                log('Skip feature {}: empty geometry'.format(feature.id()))
                continue

            new_geometry = feature.geometry()
            CompatQgis.get_inner_geometry(new_geometry).convertTo(
                QgsWkbTypes.dropZ(
                    CompatQgis.get_inner_geometry(new_geometry).wkbType() # for QGIS 2 new QgsWKBTypes::Type is returned here
                )
            )
            new_geometry.transform(
                CompatQgis.coordinate_transform_obj(qgs_vector_layer_src.crs(), import_crs, QgsProject.instance())
            )
            if has_mixed_geoms:
                new_geometry.convertToMultiType()

            # Add field values one by one. While in QGIS 2 we can just addFeature() regardless of field names, in QGIS 3 we must strictly
            # define field names where the values are copied to.
            new_feature = QgsFeature(qgs_vector_layer_dst.fields())
            new_feature.setGeometry(new_geometry)
            for field in qgs_vector_layer_src.fields():
                fname = field_name_map.get(field.name(), field.name())
                fval = feature[field.name()]
                new_feature.setAttribute(fname, fval)
            qgs_vector_layer_dst.addFeature(new_feature)

            v = round(features_counter * 100 / features_count)
            if progress < v:
                progress = v
                self._layer_status(
                    qgs_vector_layer_src.name(),
                    self.tr("preparing layer ({}%)").format(progress))

        qgs_vector_layer_dst.commitChanges()

        if len(fids_with_notvalid_geom) != 0:
                msg = QCoreApplication.translate(
                    "QGISResourceJob",
                    "We've excluded features with id {0} for layer '{1}'. Reason: invalid geometry."
                ).format(
                    "[" + ", ".join(str(fid) for fid in fids_with_notvalid_geom) + "]",
                    qgs_vector_layer_src.name()
                )

                self.warningOccurred.emit(
                    JobWarning(msg)
                )

        return qgs_vector_layer_dst, field_name_map

    def determineGeometry4MemoryLayer(self, qgs_vector_layer, has_mixed_geoms):
        geometry_type = None
        if qgs_vector_layer.geometryType() == CompatQgisGeometryType.Point:
            geometry_type = "point"
        elif qgs_vector_layer.geometryType() == CompatQgisGeometryType.Line:
            geometry_type = "linestring"
        elif qgs_vector_layer.geometryType() == CompatQgisGeometryType.Polygon:
            geometry_type = "polygon"

        # if has_multipart_geometries:
        if has_mixed_geoms:
            geometry_type = "multi" + geometry_type
        else:
            for feature in qgs_vector_layer.getFeatures():
                g = feature.geometry()
                if CompatQgis.is_geom_empty(g):
                    continue # cannot detect geom type because of empty geom
                if g.isMultipart():
                    geometry_type = "multi" + geometry_type
                break

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

    def prepareAsShape(self, qgs_vector_layer: QgsVectorLayer):
        # TODO delete if no problem with gpkg
        tmp_dir = tempfile.mkdtemp('ngw_api_prepare_import')
        tmp_shape_path = os.path.join(tmp_dir, '4import.shp')

        source_srs = qgs_vector_layer.sourceCrs()
        destination_srs = QgsCoordinateReferenceSystem.fromEpsgId(3857)

        writer = QgsVectorFileWriter(
            vectorFileName=tmp_shape_path,
            fileEncoding='UTF-8',
            fields=qgs_vector_layer.fields(),
            geometryType=qgs_vector_layer.wkbType(),
            srs=destination_srs,
            driverName='ESRI Shapefile'  # required for QGIS >= 3.0, otherwise GPKG is used
        )

        transform = None
        if source_srs != destination_srs:
            transform = QgsCoordinateTransform(
                source_srs, destination_srs, QgsProject.instance()
            )

        for feature in qgs_vector_layer.getFeatures():
            try:
                if transform is not None:
                    geometry = feature.geometry()
                    geometry.transform(transform)
                    feature.setGeometry(geometry)
                writer.addFeature(feature)
            except Exception:
                self.warningOccurred.emit(
                    JobWarning(self.tr(
                        "Feature {} haven't been added. Please check geometry"
                    ).format(feature.id()))
                )
                continue

        del writer  # save changes

        tmp = tempfile.mktemp('.zip')
        basePath = os.path.splitext(tmp_shape_path)[0]
        baseName = os.path.splitext(os.path.basename(tmp_shape_path))[0]

        self._layer_status(qgs_vector_layer.name(), self.tr("packing"))

        zf = zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED)
        for i in glob.iglob(basePath + '.*'):
            ext = os.path.splitext(i)[1]
            zf.write(i, baseName + ext)

        zf.close()
        shutil.rmtree(tmp_dir)

        return tmp

    def prepareAsJSON(self, qgs_vector_layer):
        # TODO delete if no problem with gpkg
        tmp_geojson_path = tempfile.mktemp('.geojson')

        source_srs = qgs_vector_layer.sourceCrs()
        destination_srs = QgsCoordinateReferenceSystem.fromEpsgId(3857)

        writer = QgsVectorFileWriter(
            vectorFileName=tmp_geojson_path,
            fileEncoding='UTF-8',
            fields=qgs_vector_layer.fields(),
            geometryType=qgs_vector_layer.wkbType(),
            srs=destination_srs,
            driverName='GeoJSON'
        )

        transform = None
        if source_srs != destination_srs:
            transform = QgsCoordinateTransform(
                source_srs, destination_srs, QgsProject.instance()
            )

        for feature in qgs_vector_layer.getFeatures():
            try:
                if transform is not None:
                    geometry = feature.geometry()
                    geometry.transform(transform)
                    feature.setGeometry(geometry)
                writer.addFeature(feature)
            except Exception:
                self.warningOccurred.emit(
                    JobWarning(self.tr(
                        "Feature {} haven't been added. Please check geometry"
                    ).format(feature.id()))
                )
                continue

        del writer  # save changes

        return tmp_geojson_path

    def prepareAsGPKG(self, qgs_vector_layer: QgsVectorLayer):
        tmp_gpkg_path = tempfile.mktemp('.gpkg')

        source_srs = qgs_vector_layer.sourceCrs()
        destination_srs = QgsCoordinateReferenceSystem.fromEpsgId(3857)

        writer = QgsVectorFileWriter(
            vectorFileName=tmp_gpkg_path,
            fileEncoding='UTF-8',
            fields=qgs_vector_layer.fields(),
            geometryType=qgs_vector_layer.wkbType(),
            srs=destination_srs,
            driverName='GPKG'
        )

        transform = None
        if source_srs != destination_srs:
            transform = QgsCoordinateTransform(
                source_srs, destination_srs, QgsProject.instance()
            )

        for feature in qgs_vector_layer.getFeatures():
            try:
                if transform is not None:
                    geometry = feature.geometry()
                    geometry.transform(transform)
                    feature.setGeometry(geometry)
                writer.addFeature(feature)
            except Exception:
                self.warningOccurred.emit(
                    JobWarning(self.tr(
                        "Feature {} haven't been added. Please check geometry"
                    ).format(feature.id()))
                )
                continue

        del writer  # save changes

        return tmp_gpkg_path

    def addQMLStyle(self, qml, ngw_layer_resource):
        def uploadFileCallback(total_size, readed_size):
            self.statusChanged.emit(
                self.tr("Style for \"{}\"").format(ngw_layer_resource.common.display_name)
                + " - "
                + self.tr("uploading ({}%)").format(int(readed_size * 100 / total_size))
            )

        ngw_style = ngw_layer_resource.create_qml_style(
            qml,
            uploadFileCallback
        )
        return ngw_style

    def addStyle(self, qgs_map_layer, ngw_layer_resource) -> Optional[NGWQGISStyle]:
        if qgs_map_layer.type() in (QgsMapLayer.VectorLayer, QgsMapLayer.RasterLayer):
            tmp = tempfile.mktemp('.qml')
            msg, saved = qgs_map_layer.saveNamedStyle(tmp)
            ngw_resource = self.addQMLStyle(tmp, ngw_layer_resource)
            os.remove(tmp)
            return ngw_resource
        # elif layer_type == QgsMapLayer.RasterLayer:
        #     layer_provider = qgs_map_layer.providerType()
        #     if layer_provider == 'gdal':
        #         ngw_resource = ngw_layer_resource.create_style()
        #         return ngw_resource

    def updateStyle(self, qgs_map_layer, ngw_layer_resource):
        if qgs_map_layer.type() in (QgsMapLayer.VectorLayer, QgsMapLayer.RasterLayer):
            tmp = tempfile.mktemp('.qml')
            msg, saved = qgs_map_layer.saveNamedStyle(tmp)
            self.updateQMLStyle(tmp, ngw_layer_resource)
            os.remove(tmp)

    def updateQMLStyle(self, qml, ngw_layer_resource):
        def uploadFileCallback(total_size, readed_size):
            self.statusChanged.emit(
                self.tr("Style for \"{}\"").format(ngw_layer_resource.common.display_name)
                + " - "
                + self.tr("uploading ({}%)").format(int(readed_size * 100 / total_size))
            )

        ngw_layer_resource.update_qml(
            qml,
            uploadFileCallback
        )

    def getQMLDefaultStyle(self):
        gtype = self.ngw_layer._json[self.ngw_layer.type_id]["geometry_type"]

        if gtype in ["LINESTRING", "MULTILINESTRING"]:
            return os.path.join(
                os.path.dirname(__file__),
                "qgis_styles",
                "line_style.qml"
            )
        if gtype in ["POINT", "MULTIPOINT"]:
            return os.path.join(
                os.path.dirname(__file__),
                "qgis_styles",
                "point_style.qml"
            )
        if gtype in ["POLYGON", "MULTIPOLYGON"]:
            return os.path.join(
                os.path.dirname(__file__),
                "qgis_styles",
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

    def importAttachments(self, qgs_vector_layer: QgsVectorLayer, ngw_resource: NGWVectorLayer):
        ''' Checks if the layer attributes have widgets
            of type "Attachment" and "Storage Type"
            matches "existing file" and then tries
            to import the attachment
        '''
        def uploadFileCallback(total_size, readed_size, value=None):
            self._layer_status(
                imgf,
                self.tr("uploading ({}%)").format(
                    int(readed_size * 100 / total_size if value is None else value)))

        if ngw_resource.type_id != NGWVectorLayer.type_id:
            return

        ngw_ftrs = []
        for attrInx in qgs_vector_layer.attributeList():
            editor_widget = qgs_vector_layer.editorWidgetSetup(attrInx)
            if editor_widget.type() != 'ExternalResource':
                continue

            editor_config = editor_widget.config()

            # storagetype can be str or null qvariant
            is_local = not editor_config['StorageType']
            GET_FILE_MODE = QgsFileWidget.StorageMode.GetFile
            is_file = editor_config['StorageMode'] == GET_FILE_MODE
            if is_local and is_file:
                root_dir = ''

                if editor_config['RelativeStorage'] == QgsFileWidget.RelativeStorage.RelativeProject:
                    root_dir = QgsProject.instance().homePath()
                if editor_config['RelativeStorage'] == QgsFileWidget.RelativeStorage.RelativeDefaultPath:
                    root_dir = editor_config['DefaultRoot']

                for finx, ftr in enumerate(qgs_vector_layer.getFeatures()):
                    imgf = f"{root_dir}/{ftr.attributes()[attrInx]}"
                    if os.path.isfile(imgf):
                        if len(ngw_ftrs) == 0:
                            # Lazy loading
                            ngw_ftrs = ngw_resource.get_features()

                        log(f"Load file: {imgf}")
                        uploaded_file_info = ngw_ftrs[finx].ngw_vector_layer._res_factory.connection.upload_file(
                            imgf, uploadFileCallback
                        )
                        log(f"Uploaded file info: {uploaded_file_info}")
                        id = ngw_ftrs[finx].link_attachment(uploaded_file_info)


    def overwriteQGISMapLayer(self, qgs_map_layer, ngw_layer_resource):
        layer_type = qgs_map_layer.type()

        if layer_type == qgs_map_layer.VectorLayer:
            return self.overwriteQgsVectorLayer(qgs_map_layer, ngw_layer_resource)

        return None

    def overwriteQgsVectorLayer(self, qgs_map_layer, ngw_layer_resource):
        block_size = 10
        total_count = qgs_map_layer.featureCount()

        self._layer_status(ngw_layer_resource.common.display_name, self.tr("removing all features"))
        ngw_layer_resource.delete_all_features()

        features_counter = 0
        progress = 0
        for features in self.getFeaturesPart(qgs_map_layer, ngw_layer_resource, block_size):
            ngw_layer_resource.patch_features(features)

            features_counter += len(features)
            v = int(features_counter * 100 / total_count)
            if progress < v:
                progress = v
                self._layer_status(
                    ngw_layer_resource.common.display_name,
                    self.tr("adding features ({}%)").format(progress))

    def getFeaturesPart(self, qgs_map_layer, ngw_layer_resource, pack_size):
        ngw_features=[]
        for qgsFeature in qgs_map_layer.getFeatures():
            ngw_features.append(
                NGWFeature(self.createNGWFeatureDictFromQGSFeature(ngw_layer_resource, qgsFeature, qgs_map_layer), ngw_layer_resource)
            )

            if len(ngw_features) == pack_size:
                yield ngw_features
                ngw_features = []

        if len(ngw_features) > 0:
                yield ngw_features

    def createNGWFeatureDictFromQGSFeature(self, ngw_layer_resource, qgs_feature, qgs_map_layer):
        feature_dict = {}

        # id need only for update not for create
        # feature_dict["id"] = qgs_feature.id() + 1 # Fix NGW behavior
        g = qgs_feature.geometry()
        g.transform(
            CompatQgis.coordinate_transform_obj(
                qgs_map_layer.crs(),
                QgsCoordinateReferenceSystem(ngw_layer_resource.srs(), QgsCoordinateReferenceSystem.EpsgCrsId),
                QgsProject.instance()
            )
        )
        if ngw_layer_resource.is_geom_multy():
            g.convertToMultiType()
        feature_dict["geom"] = get_wkt(g)

        attributes = {}
        for qgsField in qgs_feature.fields().toList():
            value = qgs_feature.attribute(qgsField.name())
            attributes[qgsField.name()] = CompatQt.get_clean_python_value(value)

        feature_dict["fields"] = ngw_layer_resource.construct_ngw_feature_as_json(attributes)

        return feature_dict


    def _get_ngw_geom_info(self, qgs_vector_layer):
        wkb_type = CompatQgis.get_wkb_type(qgs_vector_layer.wkbType())

        if (wkb_type == CompatQgisWkbType.WKBPoint or
            wkb_type == CompatQgisWkbType.WKBMultiPoint or
            wkb_type == CompatQgisWkbType.WKBPointZ or
            wkb_type == CompatQgisWkbType.WKBMultiPointZ):
            geom_type = 'POINT'
        elif (wkb_type == CompatQgisWkbType.WKBLineString or
            wkb_type == CompatQgisWkbType.WKBMultiLineString or
            wkb_type == CompatQgisWkbType.WKBLineStringZ or
            wkb_type == CompatQgisWkbType.WKBMultiLineStringZ):
            geom_type = 'LINESTRING'
        elif (wkb_type == CompatQgisWkbType.WKBPolygon or
            wkb_type == CompatQgisWkbType.WKBMultiPolygon or
            wkb_type == CompatQgisWkbType.WKBPolygonZ or
            wkb_type == CompatQgisWkbType.WKBMultiPolygonZ):
            geom_type = 'POLYGON'
        else:
            geom_type = None # default for NGW >= 3.8.0

        if (wkb_type in [CompatQgisWkbType.WKBMultiPoint,
            CompatQgisWkbType.WKBMultiLineString,
            CompatQgisWkbType.WKBMultiPolygon,
            CompatQgisWkbType.WKBMultiPointZ,
            CompatQgisWkbType.WKBMultiLineStringZ,
            CompatQgisWkbType.WKBMultiPolygonZ]):
            geom_is_multi = True
        else:
            geom_is_multi = False

        if (wkb_type in [CompatQgisWkbType.WKBPointZ,
            CompatQgisWkbType.WKBLineStringZ,
            CompatQgisWkbType.WKBPolygonZ,
            CompatQgisWkbType.WKBMultiPointZ,
            CompatQgisWkbType.WKBMultiLineStringZ,
            CompatQgisWkbType.WKBMultiPolygonZ]):
            geom_has_z = True
        else:
            geom_has_z = False

        return geom_type, geom_is_multi, geom_has_z


class QGISResourcesUploader(QGISResourceJob):
    def __init__(self, qgs_layer_tree_nodes, ngw_resource, iface, ngw_version=None):
        super().__init__(ngw_version)
        self.qgs_layer_tree_nodes = qgs_layer_tree_nodes
        self.ngw_resource = ngw_resource
        self.iface = iface

    def _do(self):
        ngw_webmap_root_group = NGWWebMapRoot()
        ngw_webmap_basemaps = []
        self.process_one_level_of_layers_tree(self.qgs_layer_tree_nodes, self.ngw_resource, ngw_webmap_root_group, ngw_webmap_basemaps)

        # The group was attached resources,  therefore, it is necessary to upgrade for get children flag
        self.ngw_resource.update()

    def process_one_level_of_layers_tree(self, qgs_layer_tree_nodes, ngw_resource_group, ngw_webmap_item, ngw_webmap_basemaps):
        exist_resourse_names = {}
        for r in ngw_resource_group.get_children():
            exist_resourse_names[r.common.display_name] = r

        for node in qgs_layer_tree_nodes:
            if isinstance(node, QgsLayerTreeLayer):
                if self.isSuitableLayer(node.layer()) != self.SUITABLE_LAYER:
                    continue

                is_project_uploading = isinstance(self, QGISProjectUploader)
                if not is_project_uploading or node.layer().name() not in exist_resourse_names:
                    self.add_layer(ngw_resource_group, node, ngw_webmap_item, ngw_webmap_basemaps)
                elif node.layer().name() in exist_resourse_names:
                    self.update_layer(node, exist_resourse_names[node.layer().name()])
                    exist_resourse_names.pop(node.layer().name())

            if isinstance(node, QgsLayerTreeGroup):
                if node.name() not in exist_resourse_names:
                    self.add_group(ngw_resource_group, node, ngw_webmap_item, ngw_webmap_basemaps)
                elif node.name() in exist_resourse_names:
                    exist_resourse_names.pop(node.name())

        for exist_resourse_name in exist_resourse_names:
            # need to delete
            pass

    def add_layer(
        self,
        ngw_resource_group,
        qgsLayerTreeItem: QgsLayerTreeLayer,
        ngw_webmap_item,
        ngw_webmap_basemaps
    ):
        try:
            ngw_resources = self.importQGISMapLayer(
                qgsLayerTreeItem.layer(),
                ngw_resource_group
            )
        except Exception as e:
            log('Exception during adding layer')
            if len(self.qgs_layer_tree_nodes) > 1:
                self.warningOccurred.emit(
                    JobError(
                        "Import layer \"{}\" failed. Skipped.".format(qgsLayerTreeItem.layer().name()),
                        e
                    )
                )
                return
            else:
                raise e

        for ngw_resource in ngw_resources:
            self.putAddedResourceToResult(ngw_resource)

            if ngw_resource.type_id in [NGWVectorLayer.type_id, NGWRasterLayer.type_id]:
                ngw_style = self.addStyle(
                    qgsLayerTreeItem.layer(),
                    ngw_resource
                )
                self.putAddedResourceToResult(ngw_style)

                ngw_webmap_item.appendChild(
                    NGWWebMapLayer(
                        ngw_style.common.id,
                        qgsLayerTreeItem.layer().name(),
                        CompatQgis.is_layer_checked(qgsLayerTreeItem),
                        0,
                        legend=qgsLayerTreeItem.isExpanded()
                    )
                )

                # Add style to layer, therefore, it is necessary to upgrade layer resource for get children flag
                ngw_resource.update()

                # check and import attachments
                if ngw_resource.type_id == NGWVectorLayer.type_id:
                    self.importAttachments(qgsLayerTreeItem.layer(), ngw_resource)

            elif ngw_resource.type_id == NGWWmsLayer.type_id:
                transparency = None
                if qgsLayerTreeItem.layer().type() == QgsMapLayer.RasterLayer:
                    transparency = 100 - 100 * qgsLayerTreeItem.layer().renderer().opacity()

                ngw_webmap_item.appendChild(
                    NGWWebMapLayer(
                        ngw_resource.common.id,
                        ngw_resource.common.display_name,
                        CompatQgis.is_layer_checked(qgsLayerTreeItem),
                        transparency,
                        legend=qgsLayerTreeItem.isExpanded(),
                    )
                )

            elif ngw_resource.type_id == NGWBaseMap.type_id:
                ngw_webmap_basemaps.append(ngw_resource)

    def update_layer(self, qgsLayerTreeItem, ngwVectorLayer):
        self.overwriteQGISMapLayer(qgsLayerTreeItem.layer(), ngwVectorLayer)
        self.putEditedResourceToResult(ngwVectorLayer)

        for child in  ngwVectorLayer.get_children():
            if isinstance(child, NGWQGISVectorStyle):
                self.updateStyle(qgsLayerTreeItem.layer(), child)

    def add_group(self, ngw_resource_group, qgsLayerTreeGroup, ngw_webmap_item, ngw_webmap_basemaps):
        chd_names = [ch.common.display_name for ch in ngw_resource_group.get_children()]

        group_name = qgsLayerTreeGroup.name()
        # self.statusChanged.emit("Import folder \"%s\"" % group_name)

        if group_name in chd_names:
            id = 1
            while(group_name + str(id) in chd_names):
                id += 1
            group_name += str(id)

        ngw_resource_child_group = ResourceCreator.create_group(
            ngw_resource_group,
            group_name
        )
        self.putAddedResourceToResult(ngw_resource_child_group)

        ngw_webmap_child_group = NGWWebMapGroup(
            group_name,
            qgsLayerTreeGroup.isExpanded()
        )
        ngw_webmap_item.appendChild(
            ngw_webmap_child_group
        )

        self.process_one_level_of_layers_tree(
            qgsLayerTreeGroup.children(),
            ngw_resource_child_group,
            ngw_webmap_child_group,
            ngw_webmap_basemaps
        )

        ngw_resource_child_group.update() # in order to update group items: if they have children items they should become expandable


class QGISProjectUploader(QGISResourcesUploader):
    """
        if new_group_name is None  -- Update mode

        Update:
        1. Add new
        2. Rewrite current (vector only)
        3. Remove
        4. Update map

        Update Ext (future):
        Calculate mapping of qgislayer to ngw resource
        Show map for user to edit anf cofirm it
    """
    def __init__(self, new_group_name, ngw_resource, iface, ngw_version):
        qgs_layer_tree_nodes = QgsProject.instance().layerTreeRoot().children()
        super().__init__(qgs_layer_tree_nodes, ngw_resource, iface, ngw_version)
        self.new_group_name = new_group_name

    def _do(self):
        update_mode = self.new_group_name is None

        if update_mode:
            ngw_group_resource = self.ngw_resource
            self.putEditedResourceToResult(ngw_group_resource)
        else:
            new_group_name = self.unique_resource_name(self.new_group_name, self.ngw_resource)
            ngw_group_resource = ResourceCreator.create_group(
                self.ngw_resource,
                new_group_name
            )
            self.putAddedResourceToResult(ngw_group_resource)

        ngw_webmap_root_group = NGWWebMapRoot()
        ngw_webmap_basemaps = []
        self.process_one_level_of_layers_tree(
            self.qgs_layer_tree_nodes,
            ngw_group_resource,
            ngw_webmap_root_group,
            ngw_webmap_basemaps,
        )

        if not update_mode:
            ngw_webmap = self.create_webmap(
                ngw_group_resource,
                self.new_group_name + " — webmap",
                ngw_webmap_root_group.children,
                ngw_webmap_basemaps
            )
            self.putAddedResourceToResult(ngw_webmap, is_main=True)

        # The group was attached resources,  therefore, it is necessary to upgrade for get children flag
        ngw_group_resource.update()
        self.ngw_resource.update()

    def create_webmap(self, ngw_resource, ngw_webmap_name, ngw_webmap_items, ngw_webmap_basemaps):
        self._layer_status(ngw_webmap_name, self.tr("creating"))

        rectangle = self.iface.mapCanvas().extent()
        ct = CompatQgis.coordinate_transform_obj(
            self.iface.mapCanvas().mapSettings().destinationCrs(),
            QgsCoordinateReferenceSystem(4326, QgsCoordinateReferenceSystem.EpsgCrsId),
            QgsProject.instance()
        )
        rectangle = ct.transform(rectangle)
        # log(">>> rectangle 2: " + str(rectangle.asPolygon()))
        ngw_webmap_items_as_dicts = [item.toDict() for item in ngw_webmap_items]
        ngw_resource = NGWWebMap.create_in_group(
            ngw_webmap_name,
            ngw_resource,
            ngw_webmap_items_as_dicts,
            ngw_webmap_basemaps,
            [
                rectangle.xMinimum(),
                rectangle.xMaximum(),
                rectangle.yMaximum(),
                rectangle.yMinimum(),
            ],
        )

        return ngw_resource


class MapForLayerCreater(QGISResourceJob):
    def __init__(self, ngw_layer, ngw_style_id):
        NGWResourceModelJob.__init__(self)
        self.ngw_layer = ngw_layer
        self.ngw_style_id = ngw_style_id

    def _do(self):
        if self.ngw_layer.type_id == NGWWmsLayer.type_id:
            self.create4WmsLayer()
        else:
            self.create4VectorRasterLayer()

    def create4VectorRasterLayer(self):
        if self.ngw_style_id is None:
            if self.ngw_layer.type_id == NGWVectorLayer.type_id:
                ngw_style = self._defStyleForVector(self.ngw_layer)
                self.putAddedResourceToResult(ngw_style)
                self.ngw_style_id = ngw_style.common.id

            if self.ngw_layer.type_id == NGWRasterLayer.type_id:
                ngw_style = self._defStyleForRaster(self.ngw_layer)
                self.putAddedResourceToResult(ngw_style)
                self.ngw_style_id = ngw_style.common.id

        ngw_webmap_root_group = NGWWebMapRoot()
        ngw_webmap_root_group.appendChild(
            NGWWebMapLayer(
                self.ngw_style_id,
                self.ngw_layer.common.display_name,
                True,
                0,
                legend=True
            )
        )

        ngw_group = self.ngw_layer.get_parent()

        ngw_map_name = self.unique_resource_name(
            self.ngw_layer.common.display_name + "-map",
            ngw_group
        )
        ngw_resource = NGWWebMap.create_in_group(
            ngw_map_name,
            ngw_group,
            [item.toDict() for item in ngw_webmap_root_group.children],
            [],
            bbox=self.ngw_layer.extent()
        )

        self.putAddedResourceToResult(ngw_resource, is_main=True)

    def create4WmsLayer(self):
        self.ngw_style_id = self.ngw_layer.common.id

        ngw_webmap_root_group = NGWWebMapRoot()
        ngw_webmap_root_group.appendChild(
            NGWWebMapLayer(
                self.ngw_style_id,
                self.ngw_layer.common.display_name,
                True,
                0,
                legend=True
            )
        )

        ngw_group = self.ngw_layer.get_parent()

        ngw_map_name = self.unique_resource_name(
            self.ngw_layer.common.display_name + "-map",
            ngw_group
        )

        ngw_resource = NGWWebMap.create_in_group(
            ngw_map_name,
            ngw_group,
            [item.toDict() for item in ngw_webmap_root_group.children],
            [],
        )

        self.putAddedResourceToResult(ngw_resource, is_main=True)


class QGISStyleUpdater(QGISResourceJob):
    def __init__(self, qgs_map_layer, ngw_resource):
        super().__init__()
        self.qgs_map_layer = qgs_map_layer
        self.ngw_resource = ngw_resource

    def _do(self):
        #if self.ngw_resource.type_id == NGWVectorLayer.type_id:
        self.updateStyle(self.qgs_map_layer, self.ngw_resource)
        self.putEditedResourceToResult(self.ngw_resource)


class QGISStyleAdder(QGISResourceJob):
    def __init__(self, qgs_map_layer, ngw_resource):
        super().__init__()
        self.qgs_map_layer = qgs_map_layer
        self.ngw_resource = ngw_resource

    def _do(self):
        ngw_style = self.addStyle(self.qgs_map_layer, self.ngw_resource)
        if ngw_style is None:
            return
        self.putAddedResourceToResult(ngw_style)


class NGWCreateWMSForVector(QGISResourceJob):
    def __init__(self, ngw_vector_layer, ngw_group_resource, ngw_style_id):
        super().__init__()
        self.ngw_layer = ngw_vector_layer
        self.ngw_group_resource = ngw_group_resource
        self.ngw_style_id = ngw_style_id

    def _do(self):
        if self.ngw_style_id is None:
            if self.ngw_layer.type_id == NGWVectorLayer.type_id:
                ngw_style = self._defStyleForVector(self.ngw_layer)
                self.putAddedResourceToResult(ngw_style)
                self.ngw_style_id = ngw_style.common.id

            if self.ngw_layer.type_id == NGWRasterLayer.type_id:
                ngw_style = self._defStyleForRaster(self.ngw_layer)
                self.putAddedResourceToResult(ngw_style)
                self.ngw_style_id = ngw_style.common.id

        ngw_wms_service_name = self.unique_resource_name(
            self.ngw_layer.common.display_name + "-wms-service",
            self.ngw_group_resource)

        ngw_wfs_resource = NGWWmsService.create_in_group(
            ngw_wms_service_name,
            self.ngw_group_resource,
            [(self.ngw_layer, self.ngw_style_id)],
        )

        self.putAddedResourceToResult(ngw_wfs_resource, is_main=True)


class NGWUpdateVectorLayer(QGISResourceJob):
    def __init__(self, ngw_vector_layer, qgs_map_layer):
        super().__init__()
        self.ngw_layer = ngw_vector_layer
        self.qgis_layer = qgs_map_layer

    def createNGWFeatureDictFromQGSFeature(self, qgs_feature):
        feature_dict = {}

        # id need only for update not for create
        # feature_dict["id"] = qgs_feature.id() + 1 # Fix NGW behavior
        import_crs = QgsCoordinateReferenceSystem(3857, QgsCoordinateReferenceSystem.EpsgCrsId)

        g = qgs_feature.geometry()
        if CompatQgis.is_geom_empty(g):
            return None
        g.transform(CompatQgis.coordinate_transform_obj(self.qgis_layer.crs(), import_crs, QgsProject.instance()))
        if self.ngw_layer.is_geom_multy():
            g.convertToMultiType()

        feature_dict["geom"] = get_wkt(g)

        attributes = {}
        for qgsField in qgs_feature.fields().toList():
            value = qgs_feature.attribute(qgsField.name())
            attributes[qgsField.name()] = CompatQt.get_clean_python_value(value)

        feature_dict["fields"] = self.ngw_layer.construct_ngw_feature_as_json(attributes)

        return feature_dict

    def getFeaturesPart(self, pack_size):
        ngw_features=[]
        for qgsFeature in self.qgis_layer.getFeatures():
            ngw_feature_dict = self.createNGWFeatureDictFromQGSFeature(qgsFeature)
            if ngw_feature_dict is None:
                # TODO: somehow warn user about skipped features?
                log('WARN: Feature skipped')
                continue
            ngw_features.append(NGWFeature(ngw_feature_dict, self.ngw_layer))

            if len(ngw_features) == pack_size:
                yield ngw_features
                ngw_features = []

        if len(ngw_features) > 0:
                yield ngw_features

    def _do(self):
        log(">>> NGWUpdateVectorLayer _do")
        block_size = 10
        total_count = self.qgis_layer.featureCount()

        self._layer_status(self.qgis_layer.name(), self.tr("removing all features"))
        self.ngw_layer.delete_all_features()

        features_counter = 0
        progress = 0
        for features in self.getFeaturesPart(block_size):
            self.ngw_layer.patch_features(features)

            features_counter += len(features)
            v = int(features_counter * 100 / total_count)
            if progress < v:
                progress = v
                self._layer_status(
                    self.qgis_layer.name(),
                    self.tr("adding features ({}%)").format(progress))
