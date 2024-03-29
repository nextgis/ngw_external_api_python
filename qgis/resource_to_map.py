# -*- coding: utf-8 -*-
"""
/***************************************************************************
    NextGIS WEB API
                              -------------------
        begin                : 2014-11-19
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
from typing import Dict, List, cast, Optional
from qgis.PyQt.QtCore import (
    QByteArray, QUrl, QEventLoop, QTemporaryFile, QIODevice
)
from qgis.PyQt.QtNetwork import QNetworkAccessManager, QNetworkRequest

from qgis.core import (
    QgsVectorLayer, QgsRasterLayer, QgsMapLayer, QgsProject, QgsRectangle,
    QgsEditorWidgetSetup, QgsMapLayerStyle
)

from ..core.ngw_resource import API_RESOURCE_URL, NGWResource
from ..core.ngw_vector_layer import NGWVectorLayer
from ..core.ngw_raster_layer import NGWRasterLayer
from ..core.ngw_wfs_service import NGWWfsService
from ..core.ngw_ogcf_service import NGWOgcfService
from ..core.ngw_qgis_style import NGWQGISStyle
from .qgis_ngw_connection import QgsNgwConnection

from ..utils import log

from .compat_qgis import CompatQgis


class UnsupportedRasterTypeException(Exception):
    pass


def _add_aliases(
    qgs_vector_layer: QgsVectorLayer, ngw_vector_layer: NGWVectorLayer
) -> None:
    for field_name, field_def in list(ngw_vector_layer.field_defs.items()):
        field_alias = field_def.get('display_name')
        if not field_alias:
            continue
        CompatQgis.set_field_alias(qgs_vector_layer, field_name, field_alias)


def _add_lookup_tables(
    qgs_vector_layer: QgsVectorLayer, ngw_vector_layer: NGWVectorLayer
) -> None:
    lookup_table_id_for_field: Dict[str, int] = {}

    for field_name, field_def in list(ngw_vector_layer.field_defs.items()):
        lookup_table = field_def.get('lookup_table')
        if lookup_table is None:
            continue
        lookup_table_id_for_field[field_name] = lookup_table['id']

    if len(lookup_table_id_for_field) == 0:
        return

    lookup_tables: Dict[int, List[Dict[str, str]]] = {}
    lookup_table_ids = set(lookup_table_id_for_field.values())
    for lookup_table_id in lookup_table_ids:
        connection: QgsNgwConnection = ngw_vector_layer._res_factory.connection
        lookup_url = API_RESOURCE_URL(lookup_table_id)
        try:
            result = connection.get(lookup_url)
        except Exception:
            continue

        lookup_table = result.get('lookup_table')
        if lookup_table is None:
            continue

        lookup_tables[lookup_table_id] = [
            {description: value}
            for value, description
            in lookup_table['items'].items()
        ]

    layer_fields = qgs_vector_layer.fields()
    for field_name, lookup_table_id in lookup_table_id_for_field.items():
        field_index = layer_fields.indexFromName(field_name)
        if field_index == -1 or lookup_table_id not in lookup_tables:
            continue

        setup = QgsEditorWidgetSetup(
            'ValueMap', {'map': lookup_tables[lookup_table_id]}
        )
        qgs_vector_layer.setEditorWidgetSetup(field_index, setup)


def _add_geojson_layer(resource):
    if not isinstance(resource, NGWVectorLayer):
        raise Exception('Resource type is not VectorLayer!')
    qgs_geojson_layer = QgsVectorLayer(
        resource.get_absolute_geojson_url(),
        resource.common.display_name,
        'ogr'
    )
    if not qgs_geojson_layer.isValid():
        raise Exception('Layer "{}" can\'t be added to the map!'.format(
            resource.common.display_name
        ))
    qgs_geojson_layer.dataProvider().setEncoding('UTF-8')
    return qgs_geojson_layer


def _add_cog_raster_layer(resource):
    if not isinstance(resource, NGWRasterLayer):
        raise Exception('Resource type is not raster layer!')
    if not resource.is_cog:
        raise UnsupportedRasterTypeException()
    url = '{}/cog'.format(resource.get_absolute_api_url_with_auth())
    qgs_raster_layer = QgsRasterLayer(url, resource.common.display_name, 'gdal')
    if not qgs_raster_layer.isValid():
        log('Failed to add raster layer to QGIS. URL: {}'.format(url))
        raise Exception('Layer "{}" can\'t be added to the map!'.format(
            resource.common.display_name
        ))
    return qgs_raster_layer


def _add_style_to_layer(style_resource: NGWQGISStyle, qgs_layer: QgsMapLayer):
    ev_loop = QEventLoop()
    qml_url = style_resource.download_qml_url()
    qml_req = QNetworkRequest(QUrl(qml_url))
    creds = style_resource.get_creds_for_qml()
    if creds[0] and creds[1]:
        creds_str = creds[0] + ':' + creds[1]
        authstr = creds_str.encode('utf-8')
        authstr = QByteArray(authstr).toBase64()
        authstr = QByteArray('Basic '.encode('utf-8')).append(authstr)
        qml_req.setRawHeader("Authorization".encode('utf-8'), authstr)
    dwn_qml_manager = QNetworkAccessManager()
    dwn_qml_manager.finished.connect(ev_loop.quit)
    reply = dwn_qml_manager.get(qml_req)
    ev_loop.exec_()

    assert reply is not None

    if reply.error():
        log('Failed to download QML: {}'.format(reply.errorString()))
        return

    style_xml = reply.readAll().data().decode()
    style = QgsMapLayerStyle(style_xml)
    if not style.isValid():
        log('Unable apply style to the layer')
        return

    style_manager = qgs_layer.styleManager()
    assert style_manager is not None

    style_manager.addStyle(style_resource.common.display_name, style)


def _add_all_styles_to_layer(
    qgs_layer: QgsMapLayer,
    resources: List[NGWResource],
    default_style: Optional[NGWResource] = None
) -> None:
    styles = filter(
        lambda resource: isinstance(resource, NGWQGISStyle), resources
    )
    styles = sorted(styles, key=lambda resource: resource.common.display_name)

    for style_resource in styles:
        style_resource = cast(NGWQGISStyle, style_resource)
        _add_style_to_layer(style_resource, qgs_layer)

    style_manager = qgs_layer.styleManager()
    assert style_manager is not None

    # Remove default style
    current_style_name = style_manager.currentStyle()
    style_manager.removeStyle(current_style_name)

    # Set choosen or the first one
    if default_style is not None:
        style_manager.setCurrentStyle(default_style.common.display_name)
    else:
        styles = style_manager.styles()
        if qgs_layer.name() in styles:
            style_manager.setCurrentStyle(
                styles[styles.index(qgs_layer.name())]
            )


def add_resource_as_geojson(resource, children, default_style=None):
    qgs_geojson_layer = _add_geojson_layer(resource)

    _add_all_styles_to_layer(qgs_geojson_layer, children, default_style)
    _add_aliases(qgs_geojson_layer, resource)
    _add_lookup_tables(qgs_geojson_layer, resource)

    project = QgsProject.instance()
    assert project is not None
    project.addMapLayer(qgs_geojson_layer)


def add_resource_as_cog_raster(resource, children, default_style=None):
    qgs_raster_layer = _add_cog_raster_layer(resource)

    _add_all_styles_to_layer(qgs_raster_layer, children, default_style)

    project = QgsProject.instance()
    assert project is not None
    map_layer = project.addMapLayer(qgs_raster_layer)
    if map_layer is None:
        raise Exception('Failed to add layer to QGIS')


def add_resource_as_wfs_layers(wfs_resource, return_extent=False):
    if not isinstance(wfs_resource, NGWWfsService):
        raise NGWError('Resource type is not WfsService!')

    # Extent stuff
    if return_extent:
        summary_extent = QgsRectangle()
        summary_extent.setMinimal()

    # Add group
    toc_root = QgsProject.instance().layerTreeRoot()
    layers_group = toc_root.insertGroup(0, wfs_resource.common.display_name)

    # Add layers
    for wfs_layer in wfs_resource.wfs.layers:
        url = wfs_resource.get_wfs_url(wfs_layer.keyname)
        qgs_wfs_layer = QgsVectorLayer(url, wfs_layer.display_name, 'WFS')

        ngw_vector_layer = wfs_resource.get_source_layer(wfs_layer.resource_id)

        # # Add vector style. Select the first QGIS style if several.
        vec_layer_children = ngw_vector_layer.get_children()
        _add_all_styles_to_layer(qgs_wfs_layer, vec_layer_children)

        _add_aliases(qgs_wfs_layer, ngw_vector_layer)
        _add_lookup_tables(qgs_wfs_layer, ngw_vector_layer)

        # summarize extent
        if return_extent:
            _summ_extent(summary_extent, qgs_wfs_layer)

        project = QgsProject.instance()
        assert project is not None
        project.addMapLayer(qgs_wfs_layer, False)
        layers_group.insertLayer(0, qgs_wfs_layer)

    if return_extent:
        return summary_extent


def add_ogcf_resource(ogcf_resource: NGWOgcfService):
    if not isinstance(ogcf_resource, NGWOgcfService):
        raise NGWError('Resource type is not OGCService!')

    project = QgsProject.instance()
    assert project is not None
    layer_tree_root = project.layerTreeRoot()
    assert layer_tree_root is not None
    layers_group = \
        layer_tree_root.insertGroup(0, ogcf_resource.common.display_name)
    assert layers_group is not None

    # Add layers
    for ogc_layer in ogcf_resource.ogcf.layers:
        url = ogcf_resource.get_ogcf_url(ogc_layer.keyname)
        qgis_ogc_layer = QgsVectorLayer(url, ogc_layer.display_name, 'OAPIF')

        layer_resource = ogcf_resource._res_factory.get_resource(ogc_layer.resource_id)

        # # Add vector style. Select the first QGIS style if several.
        vec_layer_children = layer_resource.get_children()
        _add_all_styles_to_layer(qgis_ogc_layer, vec_layer_children)

        _add_aliases(qgis_ogc_layer, layer_resource)
        _add_lookup_tables(qgis_ogc_layer, layer_resource)

        project.addMapLayer(qgis_ogc_layer, addToLegend=False)
        layers_group.addLayer(qgis_ogc_layer)


def _summ_extent(self, summary_extent, layer):
    layer_extent = layer.extent()

    if layer_extent.isEmpty() and layer.type() == QgsMapLayer.VectorLayer:
        layer.updateExtents()
        layer_extent = layer.extent()
