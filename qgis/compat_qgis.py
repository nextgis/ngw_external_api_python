from qgis import core
from qgis.core import Qgis as QGis
from qgis.PyQt import QtCore

COMPAT_QGIS_UNSUPPORTED_MSG = "Unsupported QGIS version"


COMPAT_QGIS_VERSION = 3
COMPAT_QT_VERSION = 5

COMPAT_PYQT_VERSION = QtCore.PYQT_VERSION_STR
COMPAT_PYQT_VERSION = COMPAT_PYQT_VERSION.split(".")


compat_qgis_msglog_levels = {
    "Info": QGis.Info,
    "Warning": QGis.Warning,
    "Critical": QGis.Critical,
}

compat_qgis_msgbar_levels = compat_qgis_msglog_levels

compat_qgis_geom_types = {
    "Point": core.QgsWkbTypes.PointGeometry,
    "Line": core.QgsWkbTypes.LineGeometry,
    "Polygon": core.QgsWkbTypes.PolygonGeometry,
    "NoGeometry": core.QgsWkbTypes.NoGeometry,
    "UnknownGeometry": core.QgsWkbTypes.UnknownGeometry,
}

compat_qgis_wkb_types = {
    "WKBPoint": core.QgsWkbTypes.Point,
    "WKBLineString": core.QgsWkbTypes.LineString,
    "WKBPolygon": core.QgsWkbTypes.Polygon,
    "WKBMultiPoint": core.QgsWkbTypes.MultiPoint,
    "WKBMultiLineString": core.QgsWkbTypes.MultiLineString,
    "WKBMultiPolygon": core.QgsWkbTypes.MultiPolygon,
    "WKBPointZ": core.QgsWkbTypes.PointZ,
    "WKBLineStringZ": core.QgsWkbTypes.LineStringZ,
    "WKBPolygonZ": core.QgsWkbTypes.PolygonZ,
    "WKBMultiPointZ": core.QgsWkbTypes.MultiPointZ,
    "WKBMultiLineStringZ": core.QgsWkbTypes.MultiLineStringZ,
    "WKBMultiPolygonZ": core.QgsWkbTypes.MultiPolygonZ,
    "WKBPoint25D": core.QgsWkbTypes.Point25D,
    "WKBLineString25D": core.QgsWkbTypes.LineString25D,
    "WKBPolygon25D": core.QgsWkbTypes.Polygon25D,
    "WKBMultiPoint25D": core.QgsWkbTypes.MultiPoint25D,
    "WKBMultiLineString25D": core.QgsWkbTypes.MultiLineString25D,
    "WKBMultiPolygon25D": core.QgsWkbTypes.MultiPolygon25D,
}


CompatQgisMsgLogLevel = type(
    "CompatQgisMsgLogLevel", (), (compat_qgis_msglog_levels)
)
CompatQgisMsgBarLevel = type(
    "CompatQgisMsgBarLevel", (), (compat_qgis_msgbar_levels)
)
CompatQgisGeometryType = type(
    "CompatQgisGeometryType", (), (compat_qgis_geom_types)
)
CompatQgisWkbType = type("CompatQgisWkbType", (), (compat_qgis_wkb_types))


class CompatQgis:
    @classmethod
    def coordinate_transform_obj(cls, crs, import_crs, project):
        if COMPAT_QGIS_VERSION == 2:
            return core.QgsCoordinateTransform(crs, import_crs)
        elif COMPAT_QGIS_VERSION == 3:
            return core.QgsCoordinateTransform(crs, import_crs, project)
        else:
            raise NotImplementedError(COMPAT_QGIS_UNSUPPORTED_MSG)

    @classmethod
    def is_geom_empty(cls, geometry):
        if COMPAT_QGIS_VERSION == 2:
            return True if geometry is None else False
        elif COMPAT_QGIS_VERSION == 3:
            return True if geometry.isNull() else False
        else:
            raise NotImplementedError(COMPAT_QGIS_UNSUPPORTED_MSG)


class CompatQt:
    @classmethod
    def has_redirect_policy(cls):
        try:
            if (
                int(COMPAT_PYQT_VERSION[0]) >= 5
                and int(COMPAT_PYQT_VERSION[1]) >= 9
            ):
                return True
            return False
        except Exception:
            return False

    @classmethod
    def get_clean_python_value(cls, v):
        if v == core.NULL:
            return None
        if isinstance(v, QtCore.QDateTime):
            return v.toPyDateTime()
        if isinstance(v, QtCore.QDate):
            return v.toPyDate()
        if isinstance(v, QtCore.QTime):
            return v.toPyTime()
        return v
