from abc import ABC

from osgeo import ogr
from qgis.core import QgsCoordinateReferenceSystem, QgsField, QgsFields
from qgis.PyQt.QtCore import QVariant

from .ngw_resource import NGWResource


class NGWAbstractVectorResource(ABC, NGWResource):
    UNKNOWN = 0
    POINT = 1
    MULTIPOINT = 2
    LINESTRING = 3
    MULTILINESTRING = 4
    POLYGON = 5
    MULTIPOLYGON = 6
    POINTZ = 7
    MULTIPOINTZ = 8
    LINESTRINGZ = 9
    MULTILINESTRINGZ = 10
    POLYGONZ = 11
    MULTIPOLYGONZ = 12

    __GEOMETRIES = {
        "POINT": POINT,
        "MULTIPOINT": MULTIPOINT,
        "LINESTRING": LINESTRING,
        "MULTILINESTRING": MULTILINESTRING,
        "POLYGON": POLYGON,
        "MULTIPOLYGON": MULTIPOLYGON,
        "POINTZ": POINTZ,
        "MULTIPOINTZ": MULTIPOINTZ,
        "LINESTRINGZ": LINESTRINGZ,
        "MULTILINESTRINGZ": MULTILINESTRINGZ,
        "POLYGONZ": POLYGONZ,
        "MULTIPOLYGONZ": MULTIPOLYGONZ,
    }

    (
        FieldTypeInteger,
        FieldTypeBigint,
        FieldTypeReal,
        FieldTypeString,
        FieldTypeDate,
        FieldTypeTime,
        FieldTypeDatetime,
    ) = ["INTEGER", "BIGINT", "REAL", "STRING", "DATE", "TIME", "DATETIME"]

    FieldTypes = [
        FieldTypeInteger,
        FieldTypeBigint,
        FieldTypeReal,
        FieldTypeString,
        FieldTypeDate,
        FieldTypeTime,
        FieldTypeDatetime,
    ]

    def __init__(self, resource_factory, resource_json):
        super().__init__(resource_factory, resource_json)

        self._field_defs = {}
        for field_def in self._json.get("feature_layer", {}).get("fields", []):
            self._field_defs[field_def.get("keyname")] = field_def

    @property
    def field_defs(self):
        return self._field_defs

    @property
    def qgs_fields(self) -> QgsFields:
        field_types = {
            self.FieldTypeInteger: QVariant.Type.Int,
            self.FieldTypeBigint: QVariant.Type.LongLong,
            self.FieldTypeReal: QVariant.Type.Double,
            self.FieldTypeString: QVariant.Type.String,
            self.FieldTypeDate: QVariant.Type.Date,
            self.FieldTypeTime: QVariant.Type.Time,
            self.FieldTypeDatetime: QVariant.Type.DateTime,
        }

        fields = QgsFields()
        for field_def in self.field_defs.values():
            field_type = field_def.get("datatype", self.FieldTypeString)
            field = QgsField(field_def.get("keyname"), field_types[field_type])
            fields.append(field)
        return fields

    def fieldType(self, name):
        field_def = self._field_defs.get(name, {})
        datatype = field_def.get("datatype")
        if datatype in self.FieldTypes:
            return datatype
        return None

    def geom_type(self):
        if self.type_id in self._json:
            if "geometry_type" in self._json[self.type_id]:
                return self.__GEOMETRIES.get(
                    self._json[self.type_id]["geometry_type"], self.UNKNOWN
                )
        return self.UNKNOWN

    @property
    def geom_name(self) -> str:
        return self._json[self.type_id]["geometry_type"]

    @property
    def wkb_geom_type(self) -> int:
        wkb_mapping = {
            self.UNKNOWN: ogr.wkbNone,
            self.POINT: ogr.wkbPoint,
            self.POINTZ: ogr.wkbPoint25D,
            self.MULTIPOINT: ogr.wkbMultiPoint,
            self.MULTIPOINTZ: ogr.wkbMultiPoint25D,
            self.LINESTRING: ogr.wkbLineString,
            self.LINESTRINGZ: ogr.wkbLineString25D,
            self.MULTILINESTRING: ogr.wkbMultiLineString,
            self.MULTILINESTRINGZ: ogr.wkbMultiLineString25D,
            self.POLYGON: ogr.wkbPolygon,
            self.POLYGONZ: ogr.wkbPolygon25D,
            self.MULTIPOLYGON: ogr.wkbMultiPolygon,
            self.MULTIPOLYGONZ: ogr.wkbMultiPolygon25D,
        }
        return wkb_mapping[self.geom_type()]

    def is_geom_multy(self):
        return self.geom_type() in [
            self.MULTIPOINT,
            self.MULTILINESTRING,
            self.MULTIPOLYGON,
        ]

    def is_geom_with_z(self):
        return self.geom_type() in [
            self.POINTZ,
            self.MULTIPOINTZ,
            self.LINESTRINGZ,
            self.MULTILINESTRINGZ,
            self.POLYGONZ,
            self.MULTIPOLYGONZ,
        ]

    def srs(self):
        return self._json.get(self.type_id, {}).get("srs", {}).get("id")

    @property
    def qgs_srs(self) -> QgsCoordinateReferenceSystem:
        srs_id = self.srs()
        if srs_id is None:
            return QgsCoordinateReferenceSystem()
        return QgsCoordinateReferenceSystem.fromEpsgId(srs_id)
