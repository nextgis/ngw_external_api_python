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

from qgis.PyQt.QtCore import *

from qgis.core import *
from qgis.gui import *

from ..qt.qt_ngw_resource_model_job import *
from ..qt.qt_ngw_resource_model_job_error import *

from ..core.ngw_webmap import NGWWebMapLayer, NGWWebMapGroup, NGWWebMapRoot
from ..core.ngw_resource_creator import ResourceCreator
from ..core.ngw_vector_layer import NGWVectorLayer
from ..core.ngw_qgis_style import NGWQGISVectorStyle
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

from ..compat_py import unquote_plus
from ..compat_py import CompatPy
from .compat_qgis import QgsWkbTypes
from .compat_qgis import CompatQgis
from .compat_qgis import CompatQt
from .compat_qgis import CompatQgisMsgLogLevel, CompatQgisMsgBarLevel
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
        NGWResourceModelJob.__init__(self)

        self.ngw_version = ngw_version

        self.sanitize_fields_names = ["id", "geom"]

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

            if not self.baseMapCreationAvailabilityCheck(ngw_group._res_factory.connection):
                raise JobError(self.tr("Your web GIS cann't create base maps."))

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
        #log(u'>>> Uploading WMS layer "{}"'.format(qgs_wms_layer.name()))

        self.statusChanged.emit(
            "\"%s\" - Import as WMS Connection " % (
                qgs_wms_layer.name(),
            )
        )

        layer_source = qgs_wms_layer.source()
        parameters = {}
        for parameter in layer_source.split('&'):
            key, value = parameter.split("=", 1) # take the first occured because sometimes e.g. "apikey=..." can be met
            value = unquote_plus(value)

            if key in parameters:
                if not isinstance(parameters[key], list):
                    parameters[key] = [parameters[key], ]

                parameters[key].append(value)
            else:
                parameters[key] = value

        if parameters.get("type", "") == "xyz":

            if not self.baseMapCreationAvailabilityCheck(ngw_group._res_factory.connection):
                raise JobError(self.tr("Your web GIS cann't create base maps."))

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

            self.statusChanged.emit(
                "\"%s\" - Import as WMS Layer " % (
                    qgs_wms_layer.name(),
                )
            )
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
            self.statusChanged.emit(
                "\"%s\" - Upload (%d%%)" % (
                    qgs_raster_layer.name(),
                    readed_size * 100 / total_size if value is None else value
                )
            )
        def createLayerCallback():
            self.statusChanged.emit(
                "\"%s\" - Create" % (
                    qgs_raster_layer.name()
                )
            )

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
            self.statusChanged.emit(
                "\"%s\" - Upload (%d%%)" % (
                    qgs_vector_layer.name(),
                    readed_size * 100 / (total_size + 0.1) if value is None else value
                )
            )
        def createLayerCallback():
            self.statusChanged.emit(
                "\"%s\" - Create" % (
                    qgs_vector_layer.name()
                )
            )

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
            self.statusChanged.emit(
                "\"%s\" - Add aliases" % qgs_vector_layer.name()
            )
            ngw_vector_layer.add_aliases(aliases)

        self.statusChanged.emit(
            "\"%s\" - Finishing" % qgs_vector_layer.name()
        )

        os.remove(filepath)

        return ngw_vector_layer


    def prepareImportFile(self, qgs_vector_layer):
        self.statusChanged.emit(
            "\"%s\" - Prepare" % qgs_vector_layer.name()
        )

        layer_has_mixed_geoms = False
        layer_has_bad_fields = False
        fids_with_notvalid_geom = []

        # Do not check geometries (rely on NGW):
        #if NgwPluginSettings.get_sanitize_fix_geometry():
        #    layer_has_mixed_geoms, fids_with_notvalid_geom = self.checkGeometry(qgs_vector_layer)

        # Check specific fields.
        if (NgwPluginSettings.get_sanitize_rename_fields() and self.hasBadFields(qgs_vector_layer) and not self.ngwSupportsAutoRenameFields()):
            log('Incorrect fields of layer will be renamed by NextGIS Connect')
            layer_has_bad_fields = True
        else:
            log('Incorrect fields of layer will NOT be renamed by NextGIS Connect')

        rename_fields_map = {}
        if layer_has_mixed_geoms or layer_has_bad_fields or (len(fids_with_notvalid_geom) > 0):
            layer, rename_fields_map = self.createLayer4Upload(qgs_vector_layer, fids_with_notvalid_geom, layer_has_mixed_geoms, layer_has_bad_fields)
        else:
            layer = qgs_vector_layer

        if layer.featureCount() == 0:
            log(u'Layer "{}" has 0 features after checking & fixing (actually skipping) geometries'.format(layer.name()))
            import_format = 'ESRI Shapefile'
        else:
            layer_provider = layer.dataProvider()
            log('Source layer\'s data provider: "{}"'.format(layer_provider.storageType()))
            if layer_provider.storageType() in ['ESRI Shapefile', 'Delimited text file']: # CSV is here due to incorrect column types defining in GeoJSON
                import_format = 'ESRI Shapefile'
            else:
                import_format = 'GeoJSON'

        log('Use "{}" format to upload to NGW'.format(import_format))
        if import_format == 'ESRI Shapefile':
            return self.prepareAsShape(layer), layer, rename_fields_map
        else:
            return self.prepareAsJSON(layer), layer, rename_fields_map


    def checkGeometry(self, qgs_vector_layer):
        has_simple_geometries = False
        has_multipart_geometries = False

        fids_with_not_valid_geom = []

        features_count = qgs_vector_layer.featureCount()
        features_counter = 0
        progress = 0
        for feature in qgs_vector_layer.getFeatures():
            v = features_counter * 100 / features_count
            if progress < v:
                progress = v
                self.statusChanged.emit(
                    "\"%s\" - Check geometry (%d%%)" % (
                        qgs_vector_layer.name(),
                        features_counter * 100 / features_count
                    )
                )
            features_counter += 1
            if feature.geometry() is None:
                fids_with_not_valid_geom.append(feature.id())
                continue

            # isGeosValid excepted to some geometries
            # if not feature.geometry().isGeosValid():
            #     log("Feature %s has not valid geometry (geos)" % str(feature.id()))
            #     fids_with_not_valid_geom.append(feature.id())

            # Fix one point line. Method isGeosValid return true for same geometry.
            if feature.geometry().type() == CompatQgisGeometryType.Line:
                g = feature.geometry()
                if g.isMultipart():
                    for polyline in g.asMultiPolyline():
                        if len(polyline) < 2:
                            fids_with_not_valid_geom.append(feature.id())
                            break
                else:
                    if len(g.asPolyline()) < 2:
                        fids_with_not_valid_geom.append(feature.id())

            elif feature.geometry().type() == CompatQgisGeometryType.Polygon:
                g = feature.geometry()
                if g.isMultipart():
                    for polygon in g.asMultiPolygon():
                        for polyline in polygon:
                            if len(polyline) < 4:
                                log("Feature %s has not valid geometry (less then 4 points)" % str(feature.id()))
                                fids_with_not_valid_geom.append(feature.id())
                                break
                else:
                    for polyline in g.asPolygon():
                        if len(polyline) < 4:
                            log("Feature %s has not valid geometry (less then 4 points)" % str(feature.id()))
                            fids_with_not_valid_geom.append(feature.id())
                            break

            if feature.geometry().isMultipart():
                has_multipart_geometries = True
            else:
                has_simple_geometries = True

            # Do not validate geometries (rely on NGW):
            # errors = feature.geometry().validateGeometry()
            # if len(errors) != 0:
            #     log("Feature %s has invalid geometry: %s" % (str(feature.id()), ', '.join(err.what() for err in errors)))
            #     fids_with_not_valid_geom.append(feature.id())

        self.statusChanged.emit(
            "\"%s\" - Check geometry (%d%%)" % (
                qgs_vector_layer.name(),
                100
            )
        )

        return (
            (has_multipart_geometries and has_simple_geometries),
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
            vers_ok = CompatPy.pep440GreaterOrEqual(self.ngw_version, NGW_AUTORENAME_FIELDS_VERS)

        if vers_ok is None:
            return False
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
        features_counter = 1
        progress = 0
        for feature in qgs_vector_layer_src.getFeatures():
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

            tmp_progress = features_counter * 100 / features_count
            if tmp_progress > progress:
                progress = tmp_progress
                self.statusChanged.emit(
                    "\"%s\" - Prepare layer for import (%d%%)" % (
                        qgs_vector_layer_src.name(),
                        features_counter * 100 / features_count
                    )
                )
            features_counter += 1

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

    def prepareAsShape(self, qgs_vector_layer):
        tmp_dir = tempfile.mkdtemp('ngw_api_prepare_import')
        tmp_shp = os.path.join(tmp_dir, '4import.shp')

        import_crs = QgsCoordinateReferenceSystem(3857, QgsCoordinateReferenceSystem.EpsgCrsId)
        QgsVectorFileWriter.writeAsVectorFormat(
            qgs_vector_layer,
            tmp_shp,
            'utf-8',
            import_crs,
            driverName='ESRI Shapefile' # required for QGIS >= 3.0, otherwise GPKG is used
        )

        tmp = tempfile.mktemp('.zip')
        basePath = os.path.splitext(tmp_shp)[0]
        baseName = os.path.splitext(os.path.basename(tmp_shp))[0]

        self.statusChanged.emit(
            "\"%s\" - Packing" % qgs_vector_layer.name()
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
        import_crs = QgsCoordinateReferenceSystem(3857, QgsCoordinateReferenceSystem.EpsgCrsId)
        QgsVectorFileWriter.writeAsVectorFormat(
            qgs_vector_layer,
            tmp,
            'utf-8',
            import_crs,
            driverName='GeoJSON'
        )

        return tmp

    def addQMLStyle(self, qml, ngw_layer_resource):
        def uploadFileCallback(total_size, readed_size):
            self.statusChanged.emit(
                "Style for \"%s\" - Upload (%d%%)" % (
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
        if layer_type == QgsMapLayer.VectorLayer or layer_type == QgsMapLayer.RasterLayer:
            tmp = tempfile.mktemp('.qml')
            self.statusChanged.emit(
                "Style for \"%s\" - Save as qml" % qgs_map_layer.name()
            )
            msg, saved = qgs_map_layer.saveNamedStyle(tmp)
            ngw_resource = self.addQMLStyle(tmp, ngw_layer_resource)
            os.remove(tmp)
            return ngw_resource
        # elif layer_type == QgsMapLayer.RasterLayer:
        #     layer_provider = qgs_map_layer.providerType()
        #     if layer_provider == 'gdal':
        #         ngw_resource = ngw_layer_resource.create_style()
        #         return ngw_resource

        return None

    def updateStyle(self, qgs_map_layer, ngw_layer_resource):
        layer_type = qgs_map_layer.type()
        if layer_type == QgsMapLayer.VectorLayer or layer_type == QgsMapLayer.RasterLayer:
            tmp = tempfile.mktemp('.qml')
            self.statusChanged.emit(
                "Style for \"%s\" - Save as qml" % qgs_map_layer.name()
            )
            msg, saved = qgs_map_layer.saveNamedStyle(tmp)
            self.updateQMLStyle(tmp, ngw_layer_resource)
            os.remove(tmp)

    def updateQMLStyle(self, qml, ngw_layer_resource):
        def uploadFileCallback(total_size, readed_size):
            self.statusChanged.emit(
                "Style for \"%s\" - Upload (%d%%)" % (
                    ngw_layer_resource.common.display_name,
                    readed_size * 100 / total_size
                )
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

    def importAttachments(self, qgs_map_layer, ngw_resource):
        ''' Checks if the layer attributes have widgets
            of type "Attachment" and "Storage Type"
            matches "existing file" and then tries
            to import the attachment
        '''
        def uploadFileCallback(total_size, readed_size, value=None):
            self.statusChanged.emit(
                "\"%s\" - Upload (%d%%)" % (
                    imgf,
                    readed_size * 100 / (total_size + 0.1) if value is None else value
                )
            )

        if ngw_resource.type_id == NGWVectorLayer.type_id:
            ngw_ftrs = ngw_resource.get_features()
            for attrInx in qgs_map_layer.attributeList():
                wgt = qgs_map_layer.editorWidgetSetup(attrInx)
                if wgt.type() == 'ExternalResource':
                    wconf = wgt.config()
                    if (not wconf['StorageType'] and
                            wconf['StorageMode'] == 0):
                        root_dir = ''
                        if wconf['RelativeStorage'] == 1:
                            root_dir = QgsProject.instance().homePath()
                        if wconf['RelativeStorage'] == 2:
                            root_dir = wconf['DefaultRoot']
                        for finx, ftr in enumerate(qgs_map_layer.getFeatures()):
                            imgf = f"{root_dir}/{ftr.attributes()[attrInx]}"
                            if os.path.isfile(imgf):
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
        current_count = 0
        done = 0

        self.statusChanged.emit(
            "\"%s\" - Remove all feature" % (
                ngw_layer_resource.common.display_name,
            )
        )
        ngw_layer_resource.delete_all_features()

        self.statusChanged.emit(
            "\"%s\" - Add features" % (
                ngw_layer_resource.common.display_name,
            )
        )
        for features in self.getFeaturesPart(qgs_map_layer, ngw_layer_resource, block_size):
            ngw_layer_resource.patch_features(features)
            current_count += len(features)

            d = current_count * 100 / total_count
            if done < d:
                done = d
                self.statusChanged.emit(
                    "\"%s\" - Add features (%d%%)" % (
                        ngw_layer_resource.common.display_name ,
                        done
                    )
                )

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

        feature_dict["fields"] = self.ngw_layer.construct_ngw_feature_as_json(attributes)

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


class QGISResourcesImporter(QGISResourceJob):
    def __init__(self, qgs_map_layers, ngw_group, ngw_version=None):
        QGISResourceJob.__init__(self, ngw_version)
        self.qgs_map_layers = qgs_map_layers
        self.ngw_group = ngw_group

    def _do(self):
        for qgs_map_layer in self.qgs_map_layers:
            ngw_resources = self.importQGISMapLayer(
                qgs_map_layer,
                self.ngw_group
            )

            for ngw_resource in ngw_resources:
                self.putAddedResourceToResult(ngw_resource, is_main=True)

                if ngw_resource.type_id in [NGWVectorLayer.type_id, NGWRasterLayer.type_id]:
                    ngw_style = self.addStyle(
                        qgs_map_layer,
                        ngw_resource
                    )
                    self.putAddedResourceToResult(ngw_style)
                    ngw_resource.update()
                
                # check and import attachments
                if ngw_resource.type_id == NGWVectorLayer.type_id:
                    self.importAttachments(qgs_map_layer, ngw_resource)

        self.ngw_group.update()


class CurrentQGISProjectImporter(QGISResourceJob):
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
        QGISResourceJob.__init__(self, ngw_version)
        self.new_group_name = new_group_name
        self.ngw_resource = ngw_resource
        self.iface = iface

    def _do(self):
        current_project = QgsProject.instance()

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
            current_project.layerTreeRoot().children(),
            ngw_group_resource,
            ngw_webmap_root_group,
            ngw_webmap_basemaps,
        )

        if not update_mode:
            self.statusChanged.emit("Import curent qgis project: create webmap")
            ngw_webmap = self.create_webmap(
                ngw_group_resource,
                self.new_group_name + "-webmap",
                ngw_webmap_root_group.children,
                ngw_webmap_basemaps
            )
            self.putAddedResourceToResult(ngw_webmap, is_main=True)

        # The group was attached resources,  therefore, it is necessary to upgrade for get children flag
        ngw_group_resource.update()
        self.ngw_resource.update()

    def process_one_level_of_layers_tree(self, qgs_layer_tree_items, ngw_resource_group, ngw_webmap_item, ngw_webmap_basemaps):
        exist_resourse_names = {}
        for r in ngw_resource_group.get_children():
            exist_resourse_names[r.common.display_name] = r

        for item in qgs_layer_tree_items:
            if isinstance(item, QgsLayerTreeLayer):
                if self.isSuitableLayer(item.layer()) != self.SUITABLE_LAYER:
                    continue

                if item.layer().name() not in exist_resourse_names:
                    self.add_layer(ngw_resource_group, item, ngw_webmap_item, ngw_webmap_basemaps)
                elif item.layer().name() in exist_resourse_names:
                    self.update_layer(item, exist_resourse_names[item.layer().name()])
                    exist_resourse_names.pop(item.layer().name())

            if isinstance(item, QgsLayerTreeGroup):
                if item.name() not in exist_resourse_names:
                    self.add_group(ngw_resource_group, item, ngw_webmap_item, ngw_webmap_basemaps)
                elif item.name() in exist_resourse_names:
                    exist_resourse_names.pop(item.name())

        for exist_resourse_name in exist_resourse_names:
            # need to delete
            pass

    def add_layer(self, ngw_resource_group, qgsLayerTreeItem, ngw_webmap_item, ngw_webmap_basemaps):
        try:
            ngw_layer_resources = self.importQGISMapLayer(
                qgsLayerTreeItem.layer(),
                ngw_resource_group
            )
        except Exception as e:
            log('Exception during adding layer')
            if NgwPluginSettings.get_force_qgis_project_import():
                self.warningOccurred.emit(
                    JobError(
                        self.tr("Import layer '%s' failed. Skipped") % qgsLayerTreeItem.layer().name(),
                        e
                    )
                )
                return
            else:
                raise e

        for ngw_layer_resource in ngw_layer_resources:
            self.putAddedResourceToResult(ngw_layer_resource)

            if ngw_layer_resource.type_id in [NGWVectorLayer.type_id, NGWRasterLayer.type_id]:
                ngw_style = self.addStyle(
                    qgsLayerTreeItem.layer(),
                    ngw_layer_resource
                )

                if ngw_style is None:
                    return
                self.putAddedResourceToResult(ngw_style)

                ngw_webmap_item.appendChild(
                    NGWWebMapLayer(
                        ngw_style.common.id,
                        qgsLayerTreeItem.layer().name(),
                        CompatQgis.is_layer_checked(qgsLayerTreeItem),
                        0
                    )
                )

                # Add style to layer, therefore, it is necessary to upgrade layer resource for get children flag
                ngw_layer_resource.update()

            elif ngw_layer_resource.type_id == NGWWmsLayer.type_id:
                transparency = None
                if qgsLayerTreeItem.layer().type() == QgsMapLayer.RasterLayer:
                    transparency = 100 - 100 * qgsLayerTreeItem.layer().renderer().opacity()

                ngw_webmap_item.appendChild(
                    NGWWebMapLayer(
                        ngw_layer_resource.common.id,
                        ngw_layer_resource.common.display_name,
                        CompatQgis.is_layer_checked(qgsLayerTreeItem),
                        transparency
                    )
                )

            elif ngw_layer_resource.type_id == NGWBaseMap.type_id:
                ngw_webmap_basemaps.append(ngw_layer_resource)

    def update_layer(self, qgsLayerTreeItem, ngwVectorLayer):
        self.overwriteQGISMapLayer(qgsLayerTreeItem.layer(), ngwVectorLayer)
        self.putEditedResourceToResult(ngwVectorLayer)

        for child in  ngwVectorLayer.get_children():
            if isinstance(child, NGWQGISVectorStyle):
                self.updateStyle(qgsLayerTreeItem.layer(), child)

    def add_group(self, ngw_resource_group, qgsLayerTreeGroup, ngw_webmap_item, ngw_webmap_basemaps):
        chd_names = [ch.common.display_name for ch in ngw_resource_group.get_children()]

        group_name = qgsLayerTreeGroup.name()
        self.statusChanged.emit("Import folder \"%s\"" % group_name)

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

    def create_webmap(self, ngw_resource, ngw_webmap_name, ngw_webmap_items, ngw_webmap_basemaps):
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

# import QGIS Group with contents
# 28/03/2023
class CurrentQGISGroupImporter(CurrentQGISProjectImporter):    
    def __init__(self, ngw_resource, iface, ngw_version):
        QGISResourceJob.__init__(self, ngw_version)        
        self.ngw_resource = ngw_resource
        self.iface = iface

    def _do(self):
        current_project = QgsProject.instance()

        ngw_group_resource = self.ngw_resource
        super().putEditedResourceToResult(ngw_group_resource)
        
        super().putAddedResourceToResult(ngw_group_resource)

        ngw_webmap_root_group = NGWWebMapRoot()
        ngw_webmap_basemaps = []
        super().process_one_level_of_layers_tree(
            self.iface.layerTreeView().selectedNodes(),
            ngw_group_resource,
            ngw_webmap_root_group,
            ngw_webmap_basemaps,
        )

        ngw_group_resource.update()
        self.ngw_resource.update()


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
                0
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
                0
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
        QGISResourceJob.__init__(self)
        self.qgs_map_layer = qgs_map_layer
        self.ngw_resource = ngw_resource

    def _do(self):
        #if self.ngw_resource.type_id == NGWVectorLayer.type_id:
        self.updateStyle(self.qgs_map_layer, self.ngw_resource)
        self.putEditedResourceToResult(self.ngw_resource)

class QGISStyleAdder(QGISResourceJob):
    def __init__(self, qgs_map_layer, ngw_resource):
        QGISResourceJob.__init__(self)
        self.qgs_map_layer = qgs_map_layer
        self.ngw_resource = ngw_resource

    def _do(self):
        ngw_style = self.addStyle(self.qgs_map_layer, self.ngw_resource)
        self.putAddedResourceToResult(ngw_style)


class NGWCreateWMSForVector(QGISResourceJob):
    def __init__(self, ngw_vector_layer, ngw_group_resource, ngw_style_id):
        NGWResourceModelJob.__init__(self)
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
    def __init__(self, ngw_vector_layer, qgs_map_layers):
        NGWResourceModelJob.__init__(self)
        self.ngw_layer = ngw_vector_layer
        self.qgis_layer = qgs_map_layers

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
        current_count = 0
        done = 0

        self.statusChanged.emit(
            "\"%s\" - Remove all feature" % (
                self.qgis_layer ,
            )
        )
        self.ngw_layer.delete_all_features()

        self.statusChanged.emit(
            "\"%s\" - Add features" % (
                self.qgis_layer ,
            )
        )
        for features in self.getFeaturesPart(block_size):
            self.ngw_layer.patch_features(features)
            current_count += len(features)

            d = current_count * 100 / total_count
            if done < d:
                done = d
                self.statusChanged.emit(
                    "\"%s\" - Add features (%d%%)" % (
                        self.qgis_layer ,
                        done
                    )
                )
