# -*- coding: utf-8 -*-

import os
import sys

from qgis.PyQt import QtCore

from qgis import core
from qgis import gui

if hasattr(core, 'QGis'):
    from qgis.core import QGis
else:
    from qgis.core import Qgis as QGis


COMPAT_QGIS_UNSUPPORTED_MSG = 'Unsupported QGIS version'


COMPAT_QGIS_VERSION = None
COMPAT_QT_VERSION = None
if QGis.QGIS_VERSION_INT >= 30000:
    COMPAT_QGIS_VERSION = 3
    COMPAT_QT_VERSION = 5
else: # currently for all versions less than 3
    COMPAT_QGIS_VERSION = 2
    COMPAT_QT_VERSION = 4

COMPAT_PYQT_VERSION = QtCore.PYQT_VERSION_STR
COMPAT_PYQT_VERSION = COMPAT_PYQT_VERSION.split('.')


if COMPAT_QGIS_VERSION == 2:
    compat_qgis_msglog_levels = {
        'Info': core.QgsMessageLog.INFO,
        'Warning': core.QgsMessageLog.WARNING,
        'Critical': core.QgsMessageLog.CRITICAL,
    }
    compat_qgis_msgbar_levels = {
        'Info': gui.QgsMessageBar.INFO,
        'Warning': gui.QgsMessageBar.WARNING,
        'Critical': gui.QgsMessageBar.CRITICAL,
    }

    compat_qgis_geom_types = {
        'Point': QGis.Point,
        'Line': QGis.Line,
        'Polygon': QGis.Polygon,
        'NoGeometry': QGis.NoGeometry,
        'UnknownGeometry': QGis.UnknownGeometry
    }

    compat_qgis_wkb_types = {
        'WKBPoint25D': QGis.WKBPoint25D,
        'WKBLineString25D': QGis.WKBLineString25D,
        'WKBPolygon25D': QGis.WKBPolygon25D,
        'WKBMultiPoint25D': QGis.WKBMultiPoint25D,
        'WKBMultiLineString25D': QGis.WKBMultiLineString25D,
        'WKBMultiPolygon25D': QGis.WKBMultiPolygon25D
    }

elif COMPAT_QGIS_VERSION == 3:
    compat_qgis_msglog_levels = {
        'Info': QGis.Info,
        'Warning': QGis.Warning,
        'Critical': QGis.Critical,
    }

    compat_qgis_msgbar_levels = compat_qgis_msglog_levels

    compat_qgis_geom_types = {
        'Point': core.QgsWkbTypes.PointGeometry,
        'Line': core.QgsWkbTypes.LineGeometry,
        'Polygon': core.QgsWkbTypes.PolygonGeometry,
        'NoGeometry': core.QgsWkbTypes.NoGeometry,
        'UnknownGeometry': core.QgsWkbTypes.UnknownGeometry
    }

    compat_qgis_wkb_types = {
        'WKBPoint25D': core.QgsWkbTypes.Point25D,
        'WKBLineString25D': core.QgsWkbTypes.LineString25D,
        'WKBPolygon25D': core.QgsWkbTypes.Polygon25D,
        'WKBMultiPoint25D': core.QgsWkbTypes.MultiPoint25D,
        'WKBMultiLineString25D': core.QgsWkbTypes.MultiLineString25D,
        'WKBMultiPolygon25D': core.QgsWkbTypes.MultiPolygon25D
    }

else:
    raise NotImplementedError(COMPAT_QGIS_UNSUPPORTED_MSG)


CompatQgisMsgLogLevel = type('CompatQgisMsgLogLevel', (), (compat_qgis_msglog_levels))
CompatQgisMsgBarLevel = type('CompatQgisMsgBarLevel', (), (compat_qgis_msgbar_levels))
CompatQgisGeometryType = type('CompatQgisGeometryType', (), (compat_qgis_geom_types))
CompatQgisWkbType = type('CompatQgisWkbType', (), (compat_qgis_wkb_types))


class CompatQgis:

    @classmethod
    def layers_registry(cls):
        if COMPAT_QGIS_VERSION == 2:
            return core.QgsMapLayerRegistry.instance()
        elif COMPAT_QGIS_VERSION == 3:
            return core.QgsProject.instance()
        else:
            raise NotImplementedError(COMPAT_QGIS_UNSUPPORTED_MSG)

    @classmethod
    def layers_tree(cls, iface):
        if COMPAT_QGIS_VERSION == 2:
            return iface.legendInterface()
        elif COMPAT_QGIS_VERSION == 3:
            return iface.layerTreeView()
        else:
            raise NotImplementedError(COMPAT_QGIS_UNSUPPORTED_MSG)

    @classmethod
    def add_legend_action(cls, iface, action, menu_name, layer_type, all_layers):
        if COMPAT_QGIS_VERSION == 2:
            iface.legendInterface().addLegendLayerAction(action, menu_name, u'', layer_type, all_layers)
        elif COMPAT_QGIS_VERSION == 3:
            iface.addCustomActionForLayerType(action, menu_name, layer_type, all_layers)
        else:
            raise NotImplementedError(COMPAT_QGIS_UNSUPPORTED_MSG)

    @classmethod
    def remove_legend_action(cls, iface, action):
        if COMPAT_QGIS_VERSION == 2:
            iface.legendInterface().removeLegendLayerAction(action)
        elif COMPAT_QGIS_VERSION == 3:
            iface.removeCustomActionForLayerType(action)
        else:
            raise NotImplementedError(COMPAT_QGIS_UNSUPPORTED_MSG)

    @classmethod
    def wkt_geometry(cls, geometry):
        if COMPAT_QGIS_VERSION == 2:
            return geometry.exportToWkt()
        elif COMPAT_QGIS_VERSION == 3:
            return geometry.asWkt()
        else:
            raise NotImplementedError(COMPAT_QGIS_UNSUPPORTED_MSG)

    @classmethod
    def coordinate_transform_obj(cls, crs, import_crs, project):
        if COMPAT_QGIS_VERSION == 2:
            return core.QgsCoordinateTransform(crs, import_crs)
        elif COMPAT_QGIS_VERSION == 3:
            return core.QgsCoordinateTransform(crs, import_crs, project)
        else:
            raise NotImplementedError(COMPAT_QGIS_UNSUPPORTED_MSG)

    @classmethod
    def set_field_alias(cls, layer, field_name, field_alias):
        if COMPAT_QGIS_VERSION == 2:
            layer.addAttributeAlias(layer.fieldNameIndex(field_name), field_alias)
        elif COMPAT_QGIS_VERSION == 3:
            layer.setFieldAlias(layer.fields().indexFromName(field_name), field_alias)
        else:
            raise NotImplementedError(COMPAT_QGIS_UNSUPPORTED_MSG)


class CompatQt:

    @classmethod
    def set_section_resize_mod(cls, header, mode):
        if COMPAT_QT_VERSION == 4:
            header.setResizeMode(mode)
        elif COMPAT_QT_VERSION == 5:
            header.setSectionResizeMode(mode)
        else:
            raise NotImplementedError(COMPAT_QGIS_UNSUPPORTED_MSG)

    @classmethod
    def get_dialog_result_path(cls, filepath):
        if COMPAT_QT_VERSION == 4:
            return filepath
        elif COMPAT_QT_VERSION == 5:
            return filepath[0]
        else:
            raise NotImplementedError(COMPAT_QGIS_UNSUPPORTED_MSG)

    @classmethod
    def has_redirect_policy(cls):
        try:
            if int(COMPAT_PYQT_VERSION[0]) >= 5 and int(COMPAT_PYQT_VERSION[1]) >= 9:
                return True
            return False
        except:
            return False



