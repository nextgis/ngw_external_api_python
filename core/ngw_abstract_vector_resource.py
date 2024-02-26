from abc import ABC
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
