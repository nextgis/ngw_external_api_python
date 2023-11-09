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
from qgis.PyQt.QtCore import (
    QByteArray, QUrl, QEventLoop, QTemporaryFile, QIODevice
)
from qgis.PyQt.QtNetwork import QNetworkAccessManager, QNetworkRequest

from qgis.core import QgsVectorLayer, QgsRasterLayer, QgsMapLayer, QgsProject, QgsRectangle
from ..core.ngw_vector_layer import NGWVectorLayer
from ..core.ngw_raster_layer import NGWRasterLayer
from ..core.ngw_wfs_service import NGWWfsService
from ..core.ngw_qgis_style import NGWQGISStyle

from ..utils import log

from .compat_qgis import CompatQgis


class UnsupportedRasterTypeException(Exception):
    pass


def _add_aliases(qgs_vector_layer, ngw_vector_layer):
    for field_name, field_def in list(ngw_vector_layer.field_defs.items()):
        field_alias = field_def.get('display_name')
        if not field_alias:
            continue
        CompatQgis.set_field_alias(qgs_vector_layer, field_name, field_alias)


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


def _apply_style(style_resource, qgs_layer):
    ev_loop = QEventLoop()
    qml_url = style_resource.download_qml_url()
    qml_req = QNetworkRequest(QUrl(qml_url))
    creds = style_resource.get_creds_for_qml()
    if creds[0] and creds[1]:
        creds_str = creds[0] + ':' + creds[1]
        authstr = creds_str.encode('utf-8')
        authstr = QByteArray(authstr).toBase64()
        authstr = QByteArray(('Basic ').encode('utf-8')).append(authstr)
        qml_req.setRawHeader(("Authorization").encode('utf-8'), authstr)
    dwn_qml_manager = QNetworkAccessManager()
    dwn_qml_manager.finished.connect(ev_loop.quit)
    reply = dwn_qml_manager.get(qml_req)
    ev_loop.exec_()

    if reply.error():
        log('Failed to download QML: {}'.format(reply.errorString()))
        return

    filename = None
    file = QTemporaryFile()
    if file.open(QIODevice.OpenModeFlag.WriteOnly):
        file.write(reply.readAll())
        filename = file.fileName()
        file.close()
    else:
        # raise NGWError()
        log('Failed to write QML to file. Unable apply style to the layer')

    if filename is not None:
        qgs_layer.loadNamedStyle(filename)


def add_resource_as_geojson(resource):
    qgs_geojson_layer = _add_geojson_layer(resource)

    _add_aliases(qgs_geojson_layer, resource)

    project = QgsProject.instance()
    assert project is not None
    project.addMapLayer(qgs_geojson_layer)


def add_resource_as_geojson_with_style(resource, style_resource):
    qgs_geojson_layer = _add_geojson_layer(resource)

    _apply_style(style_resource, qgs_geojson_layer)

    _add_aliases(qgs_geojson_layer, resource)

    project = QgsProject.instance()
    assert project is not None
    project.addMapLayer(qgs_geojson_layer)


def add_resource_as_cog_raster(resource):
    qgs_raster_layer = _add_cog_raster_layer(resource)

    project = QgsProject.instance()
    assert project is not None
    map_layer = project.addMapLayer(qgs_raster_layer)
    if map_layer is None:
        raise Exception('Failed to add layer to QGIS')


def add_resource_as_cog_raster_with_style(resource, style_resource):
    qgs_raster_layer = _add_cog_raster_layer(resource)

    _apply_style(style_resource, qgs_raster_layer)

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

        # Add vector style. Select the first QGIS style if several.
        ngw_style_res = None
        vec_layer_children = ngw_vector_layer.get_children()
        for child in vec_layer_children:
            if isinstance(child, NGWQGISStyle):
                ngw_style_res = child
                break
        if ngw_style_res is not None:
            loop = QEventLoop()
            nam = QNetworkAccessManager()
            nam.finished.connect(loop.quit)
            reply = nam.get(QNetworkRequest(
                QUrl(ngw_style_res.download_qml_url())
            ))
            loop.exec_()
            tmpfile = QTemporaryFile()
            if tmpfile.open(QIODevice.OpenModeFlag.WriteOnly):
                tmpfile.write(reply.readAll())
                tmpfile.close()
                qgs_wfs_layer.loadNamedStyle(tmpfile.fileName())

        _add_aliases(qgs_wfs_layer, ngw_vector_layer)

        #summarize extent
        if return_extent:
            _summ_extent(summary_extent, qgs_wfs_layer)

        project = QgsProject.instance()
        assert project is not None
        project.addMapLayer(qgs_wfs_layer, False)
        layers_group.insertLayer(0, qgs_wfs_layer)

    if return_extent:
        return summary_extent


def _summ_extent(self, summary_extent, layer):
    layer_extent = layer.extent()

    if layer_extent.isEmpty() and layer.type() == QgsMapLayer.VectorLayer:
        layer.updateExtents()
        layer_extent = layer.extent()

    if layer_extent.isNull():
        return
