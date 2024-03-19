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
import tempfile

try:
    from packaging import version

    parse_version = version.parse
except Exception:
    import pkg_resources

    parse_version = pkg_resources.parse_version
from collections import Counter
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, cast

from osgeo import ogr
from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsFeature,
    QgsFeatureRequest,
    QgsGeometry,
    QgsLayerTree,
    QgsLayerTreeGroup,
    QgsLayerTreeLayer,
    QgsLayerTreeNode,
    QgsMapLayer,
    QgsPluginLayer,
    QgsProject,
    QgsProviderRegistry,
    QgsRasterLayer,
    QgsVectorFileWriter,
    QgsVectorLayer,
    QgsWkbTypes,
)
from qgis.gui import QgisInterface, QgsFileWidget
from qgis.PyQt.QtCore import QCoreApplication

from nextgis_connect.logging import logger

from ..core.ngw_base_map import NGWBaseMap, NGWBaseMapExtSettings
from ..core.ngw_feature import NGWFeature
from ..core.ngw_group_resource import NGWGroupResource
from ..core.ngw_qgis_style import (
    NGWQGISStyle,
    NGWQGISVectorStyle,
)
from ..core.ngw_raster_layer import NGWRasterLayer
from ..core.ngw_resource import NGWResource
from ..core.ngw_resource_creator import ResourceCreator
from ..core.ngw_vector_layer import NGWVectorLayer
from ..core.ngw_webmap import (
    NGWWebMap,
    NGWWebMapGroup,
    NGWWebMapLayer,
    NGWWebMapRoot,
)
from ..core.ngw_wms_connection import NGWWmsConnection
from ..core.ngw_wms_layer import NGWWmsLayer
from ..core.ngw_wms_service import NGWWmsService
from ..qt.qt_ngw_resource_model_job import NGWResourceModelJob
from ..qt.qt_ngw_resource_model_job_error import JobError, JobWarning
from .compat_qgis import (
    CompatQgis,
    CompatQgisGeometryType,
    CompatQgisWkbType,
    CompatQt,
)
from .ngw_plugin_settings import NgwPluginSettings

NGW_AUTORENAME_FIELDS_VERS = "4.1.0.dev5"


def getQgsMapLayerEPSG(qgs_map_layer):
    crs = qgs_map_layer.crs().authid()
    if crs.find("EPSG:") >= 0:
        return int(crs.split(":")[1])
    return None


def yOriginTopFromQgisTmsUrl(qgs_tms_url):
    return qgs_tms_url.find("{-y}")


def get_wkt(qgis_geometry: QgsGeometry):
    wkt = qgis_geometry.asWkt()

    # if qgis_geometry.wkbType() < 0: # TODO: why this check was made?
    wkb_type = qgis_geometry.wkbType()
    wkt_fixes = {
        CompatQgisWkbType.WKBPoint25D: ("PointZ", "Point Z"),
        CompatQgisWkbType.WKBLineString25D: ("LineStringZ", "LineString Z"),
        CompatQgisWkbType.WKBPolygon25D: ("PolygonZ", "Polygon Z"),
        CompatQgisWkbType.WKBMultiPoint25D: ("MultiPointZ", "MultiPoint Z"),
        CompatQgisWkbType.WKBMultiLineString25D: (
            "MultiLineStringZ",
            "MultiLineString Z",
        ),
        CompatQgisWkbType.WKBMultiPolygon25D: (
            "MultiPolygonZ",
            "MultiPolygon Z",
        ),
    }

    if wkb_type in wkt_fixes:
        wkt = wkt.replace(*wkt_fixes[wkb_type])

    return wkt


def get_real_wkb_type(qgs_vector_layer: QgsVectorLayer):
    MAPINFO_DRIVER = "MapInfo File"
    if qgs_vector_layer.storageType() != MAPINFO_DRIVER:
        return qgs_vector_layer.wkbType()

    layer_path = qgs_vector_layer.source().split("|")[0]
    driver: ogr.Driver = ogr.GetDriverByName(MAPINFO_DRIVER)
    datasource: Optional[ogr.DataSource] = driver.Open(layer_path)
    assert datasource is not None
    layer: Optional[ogr.Layer] = datasource.GetLayer()
    assert layer is not None

    wkb_type: int = layer.GetGeomType()
    wkb_type_2d: int = (wkb_type & ~ogr.wkb25DBit) % 1000

    is_multi = False
    has_z = False

    for feature in layer:
        geometry: Optional[ogr.Geometry] = feature.GetGeometryRef()
        if geometry is None:
            continue

        feature_wkb_type = geometry.GetGeometryType()
        feature_wkb_type_2d = (feature_wkb_type & ~ogr.wkb25DBit) % 1000
        is_multi = is_multi or wkb_type_2d + 3 == feature_wkb_type_2d
        has_z = has_z or bool(feature_wkb_type & ogr.wkb25DBit)

        if is_multi and has_z:
            break

    if is_multi:
        wkb_type += 3
    if has_z:
        wkb_type |= ogr.wkb25DBit

    return wkb_type


@dataclass(frozen=True)
class ValueRelation:
    layer_id: str
    key_field: str
    value_field: str
    filter_expression: str

    @staticmethod
    def from_config(config: Dict[str, Any]) -> "ValueRelation":
        return ValueRelation(
            config["Layer"],
            config["Key"],
            config["Value"],
            config["FilterExpression"].strip(),
        )


class QGISResourceJob(NGWResourceModelJob):
    SUITABLE_LAYER = 0
    SUITABLE_LAYER_BAD_GEOMETRY = 1

    _value_relations: Set[ValueRelation]
    _lookup_tables_id: Dict[ValueRelation, int]
    _groups: Dict[QgsLayerTreeGroup, NGWGroupResource]

    def __init__(self, ngw_version=None):
        super().__init__()

        self.ngw_version = ngw_version

        self._value_relations = set()
        self._lookup_tables_id = {}
        self._groups = {}

        self.sanitize_fields_names = ["id", "geom"]

    def _layer_status(self, layer_name, status):
        self.statusChanged.emit(f""""{layer_name}" - {status}""")

    def isSuitableLayer(self, qgs_map_layer: QgsVectorLayer):
        layer_type = qgs_map_layer.type()

        if layer_type == qgs_map_layer.VectorLayer:
            if qgs_map_layer.geometryType() in [
                CompatQgisGeometryType.NoGeometry,
                CompatQgisGeometryType.UnknownGeometry,
            ]:
                return self.SUITABLE_LAYER_BAD_GEOMETRY

        return self.SUITABLE_LAYER

    def importQGISMapLayer(self, qgs_map_layer, ngw_parent_resource):
        ngw_parent_resource.update()

        layer_type = qgs_map_layer.type()

        if layer_type == qgs_map_layer.VectorLayer:
            return [
                self.importQgsVectorLayer(qgs_map_layer, ngw_parent_resource)
            ]

        elif layer_type == QgsMapLayer.RasterLayer:
            layer_data_provider = qgs_map_layer.dataProvider().name()
            if layer_data_provider == "gdal":
                return [
                    self.importQgsRasterLayer(
                        qgs_map_layer, ngw_parent_resource
                    )
                ]

            elif layer_data_provider == "wms":
                return self.importQgsWMSLayer(
                    qgs_map_layer, ngw_parent_resource
                )

        elif layer_type == QgsMapLayer.PluginLayer:
            return self.importQgsPluginLayer(
                qgs_map_layer, ngw_parent_resource
            )

        return []

    def baseMapCreationAvailabilityCheck(self, ngw_connection):
        abilities = ngw_connection.get_abilities()
        return ngw_connection.AbilityBaseMap in abilities

    def importQgsPluginLayer(self, qgs_plugin_layer, ngw_group):
        # Look for QMS plugin layer
        if (
            qgs_plugin_layer.pluginLayerType() == "PyTiledLayer"
            and hasattr(qgs_plugin_layer, "layerDef")
            and hasattr(qgs_plugin_layer.layerDef, "serviceUrl")
        ):
            logger.debug(
                f'>>> Uploading plugin layer "{qgs_plugin_layer.name()}"'
            )

            # if not self.baseMapCreationAvailabilityCheck(ngw_group._res_factory.connection):
            #     raise JobError(self.tr("Your web GIS can't create base maps."))

            new_layer_name = self.unique_resource_name(
                qgs_plugin_layer.name(), ngw_group
            )

            epsg = getattr(qgs_plugin_layer.layerDef, "epsg_crs_id", None)
            if epsg is None:
                epsg = getQgsMapLayerEPSG(qgs_plugin_layer)

            basemap_ext_settings = NGWBaseMapExtSettings(
                getattr(qgs_plugin_layer.layerDef, "serviceUrl", None),
                epsg,
                getattr(qgs_plugin_layer.layerDef, "zmin", None),
                getattr(qgs_plugin_layer.layerDef, "zmax", None),
                getattr(qgs_plugin_layer.layerDef, "yOriginTop", None),
            )

            ngw_basemap = NGWBaseMap.create_in_group(
                new_layer_name,
                ngw_group,
                qgs_plugin_layer.layerDef.serviceUrl,
                basemap_ext_settings,
            )

            return [ngw_basemap]

        return []

    def importQgsWMSLayer(self, qgs_wms_layer, ngw_group):
        logger.debug(f'>>> Uploading WMS layer "{qgs_wms_layer.name()}"')

        self._layer_status(
            qgs_wms_layer.name(), self.tr("create WMS connection")
        )

        layer_source = qgs_wms_layer.source()
        provider_metadata = QgsProviderRegistry.instance().providerMetadata(
            "wms"
        )
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
                yOriginTopFromQgisTmsUrl(parameters.get("url", "")),
            )

            ngw_basemap_name = self.unique_resource_name(
                qgs_wms_layer.name(), ngw_group
            )
            ngw_basemap = NGWBaseMap.create_in_group(
                ngw_basemap_name,
                ngw_group,
                parameters.get("url", ""),
                basemap_ext_settings,
            )
            return [ngw_basemap]
        else:
            ngw_wms_connection_name = self.unique_resource_name(
                qgs_wms_layer.name(), ngw_group
            )
            wms_connection = NGWWmsConnection.create_in_group(
                ngw_wms_connection_name,
                ngw_group,
                parameters.get("url", ""),
                parameters.get("version", "1.1.1"),
                (parameters.get("username"), parameters.get("password")),
            )

            self._layer_status(
                qgs_wms_layer.name(), self.tr("creating WMS layer")
            )

            ngw_wms_layer_name = self.unique_resource_name(
                wms_connection.common.display_name + "_layer", ngw_group
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
        new_layer_name = self.unique_resource_name(
            qgs_raster_layer.name(), ngw_parent_resource
        )
        logger.debug(
            f'>>> Uploading raster layer "{qgs_raster_layer.name()}" (with the name "{new_layer_name}")'
        )

        def uploadFileCallback(total_size, readed_size, value=None):
            if value is None:
                value = round(readed_size * 100 / total_size)
            self._layer_status(
                qgs_raster_layer.name(),
                self.tr("uploading ({}%)").format(value),
            )

        def createLayerCallback():
            self._layer_status(qgs_raster_layer.name(), self.tr("creating"))

        layer_provider = qgs_raster_layer.providerType()
        if layer_provider == "gdal":
            filepath = qgs_raster_layer.source()
            ngw_raster_layer = ResourceCreator.create_raster_layer(
                ngw_parent_resource,
                filepath,
                new_layer_name,
                NgwPluginSettings.get_upload_cog_rasters(),
                uploadFileCallback,
                createLayerCallback,
            )

            return ngw_raster_layer

    def importQgsVectorLayer(
        self,
        qgs_vector_layer: QgsVectorLayer,
        ngw_parent_resource: NGWGroupResource,
    ) -> Optional[NGWVectorLayer]:
        new_layer_name = self.unique_resource_name(
            qgs_vector_layer.name(), ngw_parent_resource
        )
        logger.debug(
            f'>>> Uploading vector layer "{qgs_vector_layer.name()}" (with the name "{new_layer_name}")'
        )

        def uploadFileCallback(total_size, readed_size, value=None):
            self._layer_status(
                qgs_vector_layer.name(),
                self.tr("uploading ({}%)").format(
                    int(
                        readed_size * 100 / total_size
                        if value is None
                        else value
                    )
                ),
            )

        def createLayerCallback():
            self._layer_status(qgs_vector_layer.name(), self.tr("creating"))

        if (
            self.isSuitableLayer(qgs_vector_layer)
            == self.SUITABLE_LAYER_BAD_GEOMETRY
        ):
            self.errorOccurred.emit(
                JobError(
                    "Vector layer '%s' has no suitable geometry"
                    % qgs_vector_layer.name()
                )
            )
            return None

        filepath, tgt_qgs_layer, rename_fields_map = self.prepareImportFile(
            qgs_vector_layer
        )
        if filepath is None:
            self.errorOccurred.emit(
                JobError(
                    "Can't prepare layer '%s'. Skipped!"
                    % qgs_vector_layer.name()
                )
            )
            return None

        ngw_vector_layer = ResourceCreator.create_vector_layer(
            ngw_parent_resource,
            filepath,
            new_layer_name,
            uploadFileCallback,
            createLayerCallback,
        )

        fields_params: Dict[str, Dict[str, Any]] = {}
        for field in qgs_vector_layer.fields():
            alias = field.alias()
            lookup_table = None
            editor_widget_setup = field.editorWidgetSetup()
            if editor_widget_setup.type() == "ValueRelation":
                config = editor_widget_setup.config()
                value_relation = ValueRelation.from_config(config)
                lookup_table = self._lookup_tables_id[value_relation]

            if len(alias) == 0 and lookup_table is None:
                continue

            field_params: Dict[str, Any] = {}
            if len(alias) > 0:
                field_params["display_name"] = alias
            if lookup_table is not None:
                field_params["lookup_table"] = dict(id=lookup_table)

            field_name = rename_fields_map.get(field.name(), field.name())
            fields_params[field_name] = field_params

        if len(fields_params) > 0:
            self._layer_status(
                qgs_vector_layer.name(), self.tr("adding aliases")
            )
            ngw_vector_layer.update_fields_params(fields_params)

        self._layer_status(qgs_vector_layer.name(), self.tr("finishing"))
        os.remove(filepath)

        return ngw_vector_layer

    def prepareImportFile(self, qgs_vector_layer):
        self._layer_status(qgs_vector_layer.name(), self.tr("preparing"))

        layer_has_mixed_geoms = False
        layer_has_bad_fields = False
        fids_with_notvalid_geom = []

        # Do not check geometries (rely on NGW):
        # if NgwPluginSettings.get_sanitize_fix_geometry():
        #    layer_has_mixed_geoms, fids_with_notvalid_geom = self.checkGeometry(qgs_vector_layer)

        # Check specific fields.
        if (
            NgwPluginSettings.get_sanitize_rename_fields()
            and self.hasBadFields(qgs_vector_layer)
            and not self.ngwSupportsAutoRenameFields()
        ):
            logger.warning(
                "Incorrect fields of layer will be renamed by NextGIS Connect"
            )
            layer_has_bad_fields = True
        else:
            logger.warning(
                "Incorrect fields of layer will NOT be renamed by NextGIS Connect"
            )

        rename_fields_map = {}
        if (
            layer_has_mixed_geoms
            or layer_has_bad_fields
            or (len(fids_with_notvalid_geom) > 0)
        ):
            layer, rename_fields_map = self.createLayer4Upload(
                qgs_vector_layer,
                fids_with_notvalid_geom,
                layer_has_mixed_geoms,
                layer_has_bad_fields,
            )
        else:
            layer = qgs_vector_layer

        return self.prepareAsGPKG(layer), layer, rename_fields_map

    def checkGeometry(self, qgs_vector_layer):
        has_simple_geometries = False
        has_multipart_geometries = False

        fids_with_not_valid_geom = []

        features_count = qgs_vector_layer.featureCount()
        progress = 0
        for features_counter, feature in enumerate(
            qgs_vector_layer.getFeatures(), start=1
        ):
            v = round(features_counter * 100 / features_count)
            if progress < v:
                progress = v
                self._layer_status(
                    qgs_vector_layer.name(),
                    self.tr("checking geometry ({}%)").format(progress),
                )

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
                elif len(geom.asPolyline()) < 2:
                    fids_with_not_valid_geom.append(fid)

            elif geom.type() == CompatQgisGeometryType.Polygon:
                if geom.isMultipart():
                    for polygon in geom.asMultiPolygon():
                        for polyline in polygon:
                            if len(polyline) < 4:
                                logger.warning(
                                    "Feature %s has not valid geometry (less then 4 points)"
                                    % str(fid)
                                )
                                fids_with_not_valid_geom.append(fid)
                                break
                else:
                    for polyline in geom.asPolygon():
                        if len(polyline) < 4:
                            logger.warning(
                                "Feature %s has not valid geometry (less then 4 points)"
                                % str(fid)
                            )
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
            fids_with_not_valid_geom,
        )

    def hasBadFields(self, qgs_vector_layer):
        exist_fields_names = [
            field.name().lower() for field in qgs_vector_layer.fields()
        ]
        common_fields = list(
            set(exist_fields_names).intersection(self.sanitize_fields_names)
        )

        return len(common_fields) > 0

    def ngwSupportsAutoRenameFields(self):
        if self.ngw_version is None:
            return False

        # A full PEP 440 comparing.
        current_ngw_version = parse_version(self.ngw_version)
        ngw_version_with_support = parse_version(NGW_AUTORENAME_FIELDS_VERS)
        vers_ok = current_ngw_version >= ngw_version_with_support

        if vers_ok:
            logger.debug(
                f'Assume that NGW of version "{self.ngw_version}" supports auto-renaming fields'
            )
            return True
        logger.debug(
            f'Assume that NGW of version "{self.ngw_version}" does NOT support auto-renaming fields'
        )

        return False

    def createLayer4Upload(
        self,
        qgs_vector_layer_src,
        fids_with_notvalid_geom,
        has_mixed_geoms,
        has_bad_fields,
    ):
        geometry_type = self.determineGeometry4MemoryLayer(
            qgs_vector_layer_src, has_mixed_geoms
        )

        field_name_map = {}
        if has_bad_fields:
            field_name_map = self.getFieldsForRename(qgs_vector_layer_src)

            if len(field_name_map) != 0:
                msg = QCoreApplication.translate(
                    "QGISResourceJob",
                    "We've renamed fields {0} for layer '{1}'. Style for this layer may become invalid.",
                ).format(
                    list(field_name_map.keys()), qgs_vector_layer_src.name()
                )

                self.warningOccurred.emit(JobWarning(msg))

        import_crs = QgsCoordinateReferenceSystem(
            4326, QgsCoordinateReferenceSystem.EpsgCrsId
        )
        qgs_vector_layer_dst = QgsVectorLayer(
            f"{geometry_type}?crs={import_crs.authid()}",
            "temp",
            "memory",
        )

        qgs_vector_layer_dst.startEditing()

        for field in qgs_vector_layer_src.fields():
            field.setName(  # TODO: does it work? At least qgs_vector_layer_src is not in edit mode now. Also we obviously don't want to change source layer names here
                field_name_map.get(field.name(), field.name())
            )
            qgs_vector_layer_dst.addAttribute(field)

        qgs_vector_layer_dst.commitChanges()
        qgs_vector_layer_dst.startEditing()
        features_count = qgs_vector_layer_src.featureCount()

        progress = 0
        for features_counter, feature in enumerate(
            qgs_vector_layer_src.getFeatures(), start=1
        ):
            if feature.id() in fids_with_notvalid_geom:
                continue

            # Additional checks for geom correctness.
            # TODO: this was done in self.checkGeometry() but we've remove using of this method. Maybe return using this method back.
            if CompatQgis.is_geom_empty(feature.geometry()):
                logger.warning(f"Skip feature {feature.id()}: empty geometry")
                continue

            new_geometry: QgsGeometry = feature.geometry()
            new_geometry.get().convertTo(
                QgsWkbTypes.dropZ(new_geometry.wkbType())
            )
            new_geometry.transform(
                CompatQgis.coordinate_transform_obj(
                    qgs_vector_layer_src.crs(),
                    import_crs,
                    QgsProject.instance(),
                )
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
                    self.tr("preparing layer ({}%)").format(progress),
                )

        qgs_vector_layer_dst.commitChanges()

        if len(fids_with_notvalid_geom) != 0:
            msg = QCoreApplication.translate(
                "QGISResourceJob",
                "We've excluded features with id {0} for layer '{1}'. Reason: invalid geometry.",
            ).format(
                "["
                + ", ".join(str(fid) for fid in fids_with_notvalid_geom)
                + "]",
                qgs_vector_layer_src.name(),
            )

            self.warningOccurred.emit(JobWarning(msg))

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
                    continue  # cannot detect geom type because of empty geom
                if g.isMultipart():
                    geometry_type = "multi" + geometry_type
                break

        return geometry_type

    def getFieldsForRename(self, qgs_vector_layer):
        field_name_map = {}

        exist_fields_names = [
            field.name() for field in qgs_vector_layer.fields()
        ]
        for field in qgs_vector_layer.fields():
            if field.name().lower() in self.sanitize_fields_names:
                new_field_name = field.name()
                suffix = 1
                while new_field_name in exist_fields_names:
                    new_field_name = field.name() + str(suffix)
                    suffix += 1
                field_name_map.update({field.name(): new_field_name})

        return field_name_map

    def prepareAsGPKG(self, qgs_vector_layer: QgsVectorLayer):
        tmp_gpkg_path = tempfile.mktemp(".gpkg")

        source_srs = qgs_vector_layer.sourceCrs()
        destination_srs = QgsCoordinateReferenceSystem.fromEpsgId(3857)

        writer = QgsVectorFileWriter(
            vectorFileName=tmp_gpkg_path,
            fileEncoding="UTF-8",
            fields=qgs_vector_layer.fields(),
            geometryType=get_real_wkb_type(qgs_vector_layer),
            srs=destination_srs,
            driverName="GPKG",
            layerOptions=(
                QgsVectorFileWriter.defaultDatasetOptions("GPKG")
                + ["SPATIAL_INDEX=NO"]
            ),
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
                    JobWarning(
                        self.tr(
                            "Feature {} haven't been added. Please check geometry"
                        ).format(feature.id())
                    )
                )
                continue

        del writer  # save changes

        return tmp_gpkg_path

    def upload_qml_file(self, ngw_layer_resource, qml_filename, style_name):
        def uploadFileCallback(total_size, readed_size):
            self.statusChanged.emit(
                self.tr('Style for "{}"').format(
                    ngw_layer_resource.common.display_name
                )
                + " - "
                + self.tr("uploading ({}%)").format(
                    int(readed_size * 100 / total_size)
                )
            )

        ngw_style = ngw_layer_resource.create_qml_style(
            qml_filename, uploadFileCallback, style_name
        )
        return ngw_style

    def addStyle(
        self, ngw_layer_resource, qgs_map_layer, style_name
    ) -> Optional[NGWQGISStyle]:
        if not isinstance(qgs_map_layer, (QgsVectorLayer, QgsRasterLayer)):
            return None

        style_manager = qgs_map_layer.styleManager()
        assert style_manager is not None

        temp_filename = tempfile.mktemp(suffix=".qml")
        with open(temp_filename, "w") as qml_file:
            qml_data = style_manager.style(style_name).xmlData()
            qml_file.write(qml_data)

        if style_manager.isDefault(style_name):
            style_name = None

        ngw_resource = self.upload_qml_file(
            ngw_layer_resource, temp_filename, style_name
        )
        os.remove(temp_filename)
        return ngw_resource

    def updateStyle(self, qgs_map_layer, ngw_layer_resource):
        if not isinstance(qgs_map_layer, (QgsVectorLayer, QgsRasterLayer)):
            return

        style_manager = qgs_map_layer.styleManager()
        assert style_manager is not None

        current_style = style_manager.currentStyle()

        temp_filename = tempfile.mktemp(suffix=".qml")
        with open(temp_filename, "w") as qml_file:
            qml_data = style_manager.style(current_style).xmlData()
            qml_file.write(qml_data)

        self.updateQMLStyle(temp_filename, ngw_layer_resource)

        os.remove(temp_filename)

    def updateQMLStyle(self, qml, ngw_layer_resource):
        def uploadFileCallback(total_size, readed_size):
            self.statusChanged.emit(
                self.tr('Style for "{}"').format(
                    ngw_layer_resource.common.display_name
                )
                + " - "
                + self.tr("uploading ({}%)").format(
                    int(readed_size * 100 / total_size)
                )
            )

        ngw_layer_resource.update_qml(qml, uploadFileCallback)

    def getQMLDefaultStyle(self):
        gtype = self.ngw_layer._json[self.ngw_layer.type_id]["geometry_type"]

        if gtype in ["LINESTRING", "MULTILINESTRING"]:
            return os.path.join(
                os.path.dirname(__file__), "qgis_styles", "line_style.qml"
            )
        if gtype in ["POINT", "MULTIPOINT"]:
            return os.path.join(
                os.path.dirname(__file__), "qgis_styles", "point_style.qml"
            )
        if gtype in ["POLYGON", "MULTIPOLYGON"]:
            return os.path.join(
                os.path.dirname(__file__), "qgis_styles", "polygon_style.qml"
            )

        return None

    def _defStyleForVector(self, ngw_layer):
        qml = self.getQMLDefaultStyle()

        if qml is None:
            self.errorOccurred.emit(
                "There is no defalut style description for create new style."
            )
            return None

        ngw_style = self.upload_qml_file(ngw_layer, qml)

        return ngw_style

    def _defStyleForRaster(self, ngw_layer):
        ngw_style = ngw_layer.create_style()
        return ngw_style

    def importAttachments(
        self, qgs_vector_layer: QgsVectorLayer, ngw_resource: NGWVectorLayer
    ):
        """Checks if the layer attributes have widgets
        of type "Attachment" and "Storage Type"
        matches "existing file" and then tries
        to import the attachment
        """

        def uploadFileCallback(total_size, readed_size, value=None):
            self._layer_status(
                imgf,
                self.tr("uploading ({}%)").format(
                    int(
                        readed_size * 100 / total_size
                        if value is None
                        else value
                    )
                ),
            )

        if ngw_resource.type_id != NGWVectorLayer.type_id:
            return

        ngw_ftrs = []
        for attrInx in qgs_vector_layer.attributeList():
            editor_widget = qgs_vector_layer.editorWidgetSetup(attrInx)
            if editor_widget.type() != "ExternalResource":
                continue

            editor_config = editor_widget.config()

            # storagetype can be str or null qvariant
            is_local = not editor_config["StorageType"]
            GET_FILE_MODE = QgsFileWidget.StorageMode.GetFile
            is_file = editor_config["StorageMode"] == GET_FILE_MODE
            if is_local and is_file:
                root_dir = ""

                if (
                    editor_config["RelativeStorage"]
                    == QgsFileWidget.RelativeStorage.RelativeProject
                ):
                    root_dir = QgsProject.instance().homePath()
                if (
                    editor_config["RelativeStorage"]
                    == QgsFileWidget.RelativeStorage.RelativeDefaultPath
                ):
                    root_dir = editor_config["DefaultRoot"]

                for finx, ftr in enumerate(qgs_vector_layer.getFeatures()):
                    imgf = f"{root_dir}/{ftr.attributes()[attrInx]}"
                    if os.path.isfile(imgf):
                        if len(ngw_ftrs) == 0:
                            # Lazy loading
                            ngw_ftrs = ngw_resource.get_features()

                        logger.debug(f"Load file: {imgf}")
                        uploaded_file_info = ngw_ftrs[
                            finx
                        ].ngw_vector_layer._res_factory.connection.upload_file(
                            imgf, uploadFileCallback
                        )
                        logger.debug(
                            f"Uploaded file info: {uploaded_file_info}"
                        )
                        ngw_ftrs[finx].link_attachment(uploaded_file_info)

    def overwriteQGISMapLayer(self, qgs_map_layer, ngw_layer_resource):
        layer_type = qgs_map_layer.type()

        if layer_type == qgs_map_layer.VectorLayer:
            return self.overwriteQgsVectorLayer(
                qgs_map_layer, ngw_layer_resource
            )

        return None

    def overwriteQgsVectorLayer(self, qgs_map_layer, ngw_layer_resource):
        block_size = 10
        total_count = qgs_map_layer.featureCount()

        self._layer_status(
            ngw_layer_resource.common.display_name,
            self.tr("removing all features"),
        )
        ngw_layer_resource.delete_all_features()

        features_counter = 0
        progress = 0
        for features in self.getFeaturesPart(
            qgs_map_layer, ngw_layer_resource, block_size
        ):
            ngw_layer_resource.patch_features(features)

            features_counter += len(features)
            v = int(features_counter * 100 / total_count)
            if progress < v:
                progress = v
                self._layer_status(
                    ngw_layer_resource.common.display_name,
                    self.tr("adding features ({}%)").format(progress),
                )

    def getFeaturesPart(self, qgs_map_layer, ngw_layer_resource, pack_size):
        ngw_features = []
        for qgsFeature in qgs_map_layer.getFeatures():
            ngw_features.append(
                NGWFeature(
                    self.createNGWFeatureDictFromQGSFeature(
                        ngw_layer_resource, qgsFeature, qgs_map_layer
                    ),
                    ngw_layer_resource,
                )
            )

            if len(ngw_features) == pack_size:
                yield ngw_features
                ngw_features = []

        if len(ngw_features) > 0:
            yield ngw_features

    def createNGWFeatureDictFromQGSFeature(
        self, ngw_layer_resource, qgs_feature, qgs_map_layer
    ):
        feature_dict = {}

        # id need only for update not for create
        # feature_dict["id"] = qgs_feature.id() + 1 # Fix NGW behavior
        g = qgs_feature.geometry()
        g.transform(
            CompatQgis.coordinate_transform_obj(
                qgs_map_layer.crs(),
                QgsCoordinateReferenceSystem(
                    ngw_layer_resource.srs(),
                    QgsCoordinateReferenceSystem.EpsgCrsId,
                ),
                QgsProject.instance(),
            )
        )
        if ngw_layer_resource.is_geom_multy():
            g.convertToMultiType()
        feature_dict["geom"] = get_wkt(g)

        attributes = {}
        for qgsField in qgs_feature.fields().toList():
            value = qgs_feature.attribute(qgsField.name())
            attributes[qgsField.name()] = CompatQt.get_clean_python_value(
                value
            )

        feature_dict["fields"] = (
            ngw_layer_resource.construct_ngw_feature_as_json(attributes)
        )

        return feature_dict


class QGISResourcesUploader(QGISResourceJob):
    def __init__(
        self,
        qgs_layer_tree_nodes: List[QgsLayerTreeNode],
        parent_group_resource: NGWGroupResource,
        iface: QgisInterface,
        ngw_version=None,
    ):
        super().__init__(ngw_version)
        self.qgs_layer_tree_nodes = qgs_layer_tree_nodes
        self.parent_group_resource = parent_group_resource
        self.iface = iface

    def _do(self):
        self._find_lookup_tables()
        self._check_quote()

        self._add_group_tree()
        self._add_lookup_tables()

        ngw_webmap_root_group = NGWWebMapRoot()
        ngw_webmap_basemaps = []
        self.process_one_level_of_layers_tree(
            self.qgs_layer_tree_nodes,
            self.parent_group_resource,
            ngw_webmap_root_group,
            ngw_webmap_basemaps,
        )

        # The group was attached resources,  therefore, it is necessary to upgrade for get children flag
        self.parent_group_resource.update()

    def _check_quote(self, add_map: bool = False) -> None:
        def resource_type_for_layer(node: QgsLayerTreeNode) -> Optional[str]:
            layer = cast(QgsLayerTreeLayer, node).layer()
            if isinstance(layer, QgsVectorLayer):
                return "vector_layer"
            if isinstance(layer, QgsRasterLayer):
                data_provider = layer.dataProvider().name()  # type: ignore
                if data_provider == "gdal":
                    return "raster_layer"
                if data_provider == "wms":
                    registry = QgsProviderRegistry.instance()
                    provider_metadata = registry.providerMetadata("wms")
                    parameters = provider_metadata.decodeUri(layer.source())
                    return (
                        "basemap_layer"
                        if parameters.get("type") == "xyz"
                        else "wmsclient_layer"
                    )
            if isinstance(layer, QgsPluginLayer):
                return "basemap_layer"
            return None

        def resource_type_for_node(
            node: QgsLayerTreeNode,
        ) -> List[Optional[str]]:
            if node.nodeType() == QgsLayerTreeNode.NodeType.NodeLayer:
                return [resource_type_for_layer(node)]

            layers_node: List[Optional[str]] = []
            for child in node.children():
                if child.nodeType() == QgsLayerTreeNode.NodeType.NodeLayer:
                    layers_node.append(resource_type_for_layer(child))
                else:
                    layers_node.extend(resource_type_for_node(child))
            return layers_node

        resources_type = []
        for node in self.qgs_layer_tree_nodes:
            resources_type.extend(resource_type_for_node(node))

        counter = Counter(resources_type)
        counter["lookup_table"] = len(self._value_relations)
        if add_map:
            counter["webmap"] = 1
        del counter[None]

        result = self.parent_group_resource._res_factory.connection.post(
            "/api/component/resource/check_quota", counter
        )
        if not result["success"]:
            raise JobError(result["message"])

    def _find_lookup_tables(self) -> None:
        def collect_value_relations(layer_node: QgsLayerTreeNode) -> None:
            layer_node = cast(QgsLayerTreeLayer, layer_node)
            layer = layer_node.layer()
            assert layer is not None
            if not isinstance(layer, QgsVectorLayer):
                return

            for attribute_index in layer.attributeList():
                editor_widget_setup = layer.editorWidgetSetup(attribute_index)
                if editor_widget_setup.type() != "ValueRelation":
                    continue
                self._value_relations.add(
                    ValueRelation.from_config(editor_widget_setup.config())
                )

        for node in self.qgs_layer_tree_nodes:
            if QgsLayerTree.isLayer(node):
                collect_value_relations(node)
            else:
                group_node = cast(QgsLayerTreeGroup, node)
                for layer_node in group_node.findLayers():
                    collect_value_relations(layer_node)

    def process_one_level_of_layers_tree(
        self,
        qgs_layer_tree_nodes,
        ngw_resource_group,
        ngw_webmap_item,
        ngw_webmap_basemaps,
    ):
        for node in qgs_layer_tree_nodes:
            if isinstance(node, QgsLayerTreeLayer):
                if self.isSuitableLayer(node.layer()) != self.SUITABLE_LAYER:
                    continue
                layer = node.layer()
                assert layer is not None
                self.add_layer(
                    ngw_resource_group,
                    node,
                    ngw_webmap_item,
                    ngw_webmap_basemaps,
                )
            else:
                self.add_group(
                    ngw_resource_group,
                    node,
                    ngw_webmap_item,
                    ngw_webmap_basemaps,
                )

    def _add_group_tree(self) -> None:
        self.statusChanged.emit(self.tr("A group tree is being created"))
        for node in self.qgs_layer_tree_nodes:
            if not QgsLayerTree.isGroup(node):
                continue
            self.__add_group_level(
                self.parent_group_resource, cast(QgsLayerTreeGroup, node)
            )

    def __add_group_level(
        self,
        parent_group_resource: NGWGroupResource,
        group_node: QgsLayerTreeGroup,
    ) -> None:
        group_name = self.unique_resource_name(
            group_node.name(), parent_group_resource
        )

        child_group_resource = ResourceCreator.create_group(
            parent_group_resource, group_name
        )
        self.putAddedResourceToResult(child_group_resource)
        self._groups[group_node] = child_group_resource

        for node in group_node.children():
            if not QgsLayerTree.isGroup(node):
                continue
            self.__add_group_level(
                child_group_resource, cast(QgsLayerTreeGroup, node)
            )

    def _add_lookup_tables(self) -> None:
        def extract_items(
            layer_node: QgsLayerTreeLayer, value_relation: ValueRelation
        ) -> Dict[str, str]:
            layer = layer_node.layer()
            assert layer is not None
            layer = cast(QgsVectorLayer, layer)
            request = QgsFeatureRequest()
            if len(value_relation.filter_expression) > 0:
                request.setFilterExpression(value_relation.filter_expression)
            result: Dict[str, str] = {}
            for feature in layer.getFeatures(request):  # type: ignore
                key = feature[value_relation.key_field]
                value = feature[value_relation.value_field]
                result[key] = value
            return result

        project = QgsProject.instance()
        assert project is not None
        root = project.layerTreeRoot()
        assert root is not None
        for value_relation in self._value_relations:
            layer_node = root.findLayer(value_relation.layer_id)
            assert layer_node is not None

            parent_node = cast(
                Optional[QgsLayerTreeGroup], layer_node.parent()
            )
            parent_group_resource = self._groups.get(
                parent_node,
                self.parent_group_resource,  # type: ignore
            )

            lookup_table_name = self.unique_resource_name(
                layer_node.name(), parent_group_resource
            )
            lookup_table = ResourceCreator.create_lookup_table(
                lookup_table_name,
                extract_items(layer_node, value_relation),
                parent_group_resource,
            )
            self._lookup_tables_id[value_relation] = lookup_table.common.id
            self.putAddedResourceToResult(lookup_table)

    def add_layer(
        self,
        ngw_resource_group,
        layer_tree_item: QgsLayerTreeLayer,
        ngw_webmap_item,
        ngw_webmap_basemaps,
    ):
        try:
            ngw_resources = self.importQGISMapLayer(
                layer_tree_item.layer(), ngw_resource_group
            )
        except Exception as e:
            logger.exception("Exception during adding layer")

            has_several_elements = len(self.qgs_layer_tree_nodes) > 1
            group_selected = len(
                self.qgs_layer_tree_nodes
            ) == 1 and isinstance(
                self.qgs_layer_tree_nodes[0], QgsLayerTreeGroup
            )

            if has_several_elements or group_selected:
                self.warningOccurred.emit(
                    JobError(
                        f'Uploading layer "{layer_tree_item.layer().name()}" failed. Skipped.',
                        e,
                    )
                )
                return
            else:
                raise e

        for ngw_resource in ngw_resources:
            self.putAddedResourceToResult(ngw_resource)

            if ngw_resource.type_id in [
                NGWVectorLayer.type_id,
                NGWRasterLayer.type_id,
            ]:
                qgs_map_layer = layer_tree_item.layer()
                assert qgs_map_layer is not None
                style_manager = qgs_map_layer.styleManager()
                assert style_manager is not None
                current_style = style_manager.currentStyle()

                for style_name in style_manager.styles():
                    ngw_style = self.addStyle(
                        ngw_resource, qgs_map_layer, style_name
                    )
                    if ngw_style is None:
                        continue

                    self.putAddedResourceToResult(ngw_style)

                    if style_name == current_style:
                        ngw_webmap_item.appendChild(
                            NGWWebMapLayer(
                                ngw_style.common.id,
                                layer_tree_item.layer().name(),
                                layer_tree_item.itemVisibilityChecked(),
                                0,
                                legend=layer_tree_item.isExpanded(),
                            )
                        )

                # Add style to layer, therefore, it is necessary to upgrade layer resource for get children flag
                ngw_resource.update()

                # check and import attachments
                if ngw_resource.type_id == NGWVectorLayer.type_id:
                    self.importAttachments(
                        layer_tree_item.layer(), ngw_resource
                    )

            elif ngw_resource.type_id == NGWWmsLayer.type_id:
                transparency = None
                if layer_tree_item.layer().type() == QgsMapLayer.RasterLayer:
                    transparency = (
                        100
                        - 100 * layer_tree_item.layer().renderer().opacity()
                    )

                ngw_webmap_item.appendChild(
                    NGWWebMapLayer(
                        ngw_resource.common.id,
                        ngw_resource.common.display_name,
                        layer_tree_item.itemVisibilityChecked(),
                        transparency,
                        legend=layer_tree_item.isExpanded(),
                    )
                )

            elif ngw_resource.type_id == NGWBaseMap.type_id:
                ngw_webmap_basemaps.append(ngw_resource)

    def update_layer(self, qgsLayerTreeItem, ngwVectorLayer):
        self.overwriteQGISMapLayer(qgsLayerTreeItem.layer(), ngwVectorLayer)
        self.putEditedResourceToResult(ngwVectorLayer)

        for child in ngwVectorLayer.get_children():
            if isinstance(child, NGWQGISVectorStyle):
                self.updateStyle(qgsLayerTreeItem.layer(), child)

    def add_group(
        self,
        ngw_resource_group,
        qgsLayerTreeGroup,
        ngw_webmap_item,
        ngw_webmap_basemaps,
    ) -> None:
        ngw_resource_child_group = self._groups[qgsLayerTreeGroup]

        ngw_webmap_child_group = NGWWebMapGroup(
            ngw_resource_child_group.common.display_name,
            qgsLayerTreeGroup.isExpanded(),
        )
        ngw_webmap_item.appendChild(ngw_webmap_child_group)

        self.process_one_level_of_layers_tree(
            qgsLayerTreeGroup.children(),
            ngw_resource_child_group,
            ngw_webmap_child_group,
            ngw_webmap_basemaps,
        )

        ngw_resource_child_group.update()  # in order to update group items: if they have children items they should become expandable


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

    def __init__(
        self,
        new_group_name: str,
        parent_group_resource: NGWGroupResource,
        iface: QgisInterface,
        ngw_version,
    ) -> None:
        qgs_layer_tree_nodes = QgsProject.instance().layerTreeRoot().children()
        super().__init__(
            qgs_layer_tree_nodes, parent_group_resource, iface, ngw_version
        )
        self.new_group_name = new_group_name

    def _do(self):
        self._find_lookup_tables()
        self._check_quote(add_map=True)

        new_group_name = self.unique_resource_name(
            self.new_group_name, self.parent_group_resource
        )
        ngw_group_resource = ResourceCreator.create_group(
            self.parent_group_resource, new_group_name
        )
        self.putAddedResourceToResult(ngw_group_resource)
        self.parent_group_resource = ngw_group_resource

        self._add_group_tree()
        self._add_lookup_tables()

        ngw_webmap_root_group = NGWWebMapRoot()
        ngw_webmap_basemaps = []
        self.process_one_level_of_layers_tree(
            self.qgs_layer_tree_nodes,
            ngw_group_resource,
            ngw_webmap_root_group,
            ngw_webmap_basemaps,
        )

        ngw_webmap = self.create_webmap(
            ngw_group_resource,
            self.new_group_name + " — webmap",
            ngw_webmap_root_group.children,
            ngw_webmap_basemaps,
        )
        self.putAddedResourceToResult(ngw_webmap, is_main=True)

        # The group was attached resources,  therefore, it is necessary to upgrade for get children flag
        ngw_group_resource.update()
        self.parent_group_resource.update()

    def create_webmap(
        self,
        ngw_resource,
        ngw_webmap_name,
        ngw_webmap_items,
        ngw_webmap_basemaps,
    ):
        self._layer_status(ngw_webmap_name, self.tr("creating"))

        rectangle = self.iface.mapCanvas().extent()
        ct = CompatQgis.coordinate_transform_obj(
            self.iface.mapCanvas().mapSettings().destinationCrs(),
            QgsCoordinateReferenceSystem(
                4326, QgsCoordinateReferenceSystem.EpsgCrsId
            ),
            QgsProject.instance(),
        )
        rectangle = ct.transform(rectangle)
        ngw_webmap_items_as_dicts = [
            item.toDict() for item in ngw_webmap_items
        ]
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
        super().__init__()
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
                legend=True,
            )
        )

        ngw_group = self.ngw_layer.get_parent()

        ngw_map_name = self.unique_resource_name(
            self.ngw_layer.common.display_name + "-map", ngw_group
        )
        ngw_resource = NGWWebMap.create_in_group(
            ngw_map_name,
            ngw_group,
            [item.toDict() for item in ngw_webmap_root_group.children],
            [],
            bbox=self.ngw_layer.extent(),
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
                legend=True,
            )
        )

        ngw_group = self.ngw_layer.get_parent()

        ngw_map_name = self.unique_resource_name(
            self.ngw_layer.common.display_name + "-map", ngw_group
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
        # if self.ngw_resource.type_id == NGWVectorLayer.type_id:
        self.updateStyle(self.qgs_map_layer, self.ngw_resource)
        self.putEditedResourceToResult(self.ngw_resource)


class QGISStyleAdder(QGISResourceJob):
    def __init__(self, qgs_map_layer: QgsMapLayer, ngw_resource: NGWResource):
        super().__init__()
        self.qgs_map_layer = qgs_map_layer
        self.ngw_resource = ngw_resource

    def _do(self):
        style_manager = self.qgs_map_layer.styleManager()
        assert style_manager is not None

        ngw_style = self.addStyle(
            self.ngw_resource, self.qgs_map_layer, style_manager.currentStyle()
        )
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
            self.ngw_layer.common.display_name + " — WMS service",
            self.ngw_group_resource,
        )

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
        import_crs = QgsCoordinateReferenceSystem(
            3857, QgsCoordinateReferenceSystem.EpsgCrsId
        )

        g = qgs_feature.geometry()
        if CompatQgis.is_geom_empty(g):
            return None
        g.transform(
            CompatQgis.coordinate_transform_obj(
                self.qgis_layer.crs(), import_crs, QgsProject.instance()
            )
        )
        if self.ngw_layer.is_geom_multy():
            g.convertToMultiType()

        feature_dict["geom"] = get_wkt(g)

        attributes = {}
        for qgsField in qgs_feature.fields().toList():
            value = qgs_feature.attribute(qgsField.name())
            attributes[qgsField.name()] = CompatQt.get_clean_python_value(
                value
            )

        feature_dict["fields"] = self.ngw_layer.construct_ngw_feature_as_json(
            attributes
        )

        return feature_dict

    def getFeaturesPart(self, pack_size):
        ngw_features = []
        for qgsFeature in self.qgis_layer.getFeatures():
            ngw_feature_dict = self.createNGWFeatureDictFromQGSFeature(
                qgsFeature
            )
            if ngw_feature_dict is None:
                # TODO: somehow warn user about skipped features?
                logger.warning("Feature skipped")
                continue
            ngw_features.append(NGWFeature(ngw_feature_dict, self.ngw_layer))

            if len(ngw_features) == pack_size:
                yield ngw_features
                ngw_features = []

        if len(ngw_features) > 0:
            yield ngw_features

    def _do(self):
        logger.debug(">>> NGWUpdateVectorLayer _do")
        block_size = 10
        total_count = self.qgis_layer.featureCount()

        self._layer_status(
            self.qgis_layer.name(), self.tr("removing all features")
        )
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
                    self.tr("adding features ({}%)").format(progress),
                )
