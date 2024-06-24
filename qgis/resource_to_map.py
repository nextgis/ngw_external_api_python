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

from typing import Dict, List, Optional, cast

from qgis.core import (
    QgsEditorWidgetSetup,
    QgsMapLayer,
    QgsMapLayerStyle,
    QgsNetworkAccessManager,
    QgsProject,
    QgsProviderRegistry,
    QgsRasterLayer,
    QgsVectorLayer,
)
from qgis.PyQt.QtCore import (
    QUrl,
)
from qgis.PyQt.QtNetwork import QNetworkRequest

from nextgis_connect.logging import logger
from nextgis_connect.ngw_api.core.ngw_abstract_vector_resource import (
    NGWAbstractVectorResource,
)
from nextgis_connect.ngw_api.core.ngw_error import NGWError
from nextgis_connect.ngw_api.core.ngw_ogcf_service import NGWOgcfService
from nextgis_connect.ngw_api.core.ngw_qgis_style import NGWQGISStyle
from nextgis_connect.ngw_api.core.ngw_raster_layer import NGWRasterLayer
from nextgis_connect.ngw_api.core.ngw_resource import (
    API_RESOURCE_URL,
)
from nextgis_connect.ngw_api.core.ngw_vector_layer import NGWVectorLayer
from nextgis_connect.ngw_api.core.ngw_wfs_service import NGWWfsService
from nextgis_connect.ngw_connection.ngw_connections_manager import (
    NgwConnectionsManager,
)

from .qgis_ngw_connection import QgsNgwConnection


class UnsupportedRasterTypeException(Exception):
    pass


def _add_aliases(
    qgs_vector_layer: QgsVectorLayer,
    ngw_vector_layer: NGWAbstractVectorResource,
) -> None:
    for field in ngw_vector_layer.fields:
        if field.display_name is None:
            continue
        qgs_vector_layer.setFieldAlias(
            qgs_vector_layer.fields().indexFromName(field.keyname),
            field.display_name,
        )


def _add_lookup_tables(
    qgs_vector_layer: QgsVectorLayer,
    ngw_vector_layer: NGWAbstractVectorResource,
) -> None:
    lookup_table_id_for_field: Dict[str, int] = {}

    for field in ngw_vector_layer.fields:
        if field.lookup_table is None:
            continue
        lookup_table_id_for_field[field.keyname] = field.lookup_table

    if len(lookup_table_id_for_field) == 0:
        return

    lookup_tables: Dict[int, List[Dict[str, str]]] = {}
    lookup_table_ids = set(lookup_table_id_for_field.values())
    for lookup_table_id in lookup_table_ids:
        connection: QgsNgwConnection = ngw_vector_layer.res_factory.connection
        lookup_url = API_RESOURCE_URL(lookup_table_id)
        try:
            result = connection.get(lookup_url)
        except Exception:
            continue

        lookup_table = result.get("lookup_table")
        if lookup_table is None:
            continue

        lookup_tables[lookup_table_id] = [
            {description: value}
            for value, description in lookup_table["items"].items()
        ]

    layer_fields = qgs_vector_layer.fields()
    for field_name, lookup_table_id in lookup_table_id_for_field.items():
        field_index = layer_fields.indexFromName(field_name)
        if field_index == -1 or lookup_table_id not in lookup_tables:
            continue

        setup = QgsEditorWidgetSetup(
            "ValueMap", {"map": lookup_tables[lookup_table_id]}
        )
        qgs_vector_layer.setEditorWidgetSetup(field_index, setup)


def _add_geojson_layer(resource: NGWVectorLayer):
    qgs_geojson_layer = QgsVectorLayer(
        resource.get_absolute_geojson_url(),
        resource.common.display_name,
        "ogr",
    )
    if not qgs_geojson_layer.isValid():
        raise Exception(
            f'Layer "{resource.common.display_name}" can\'t be added to the map!'
        )
    qgs_geojson_layer.dataProvider().setEncoding("UTF-8")
    return qgs_geojson_layer


def _add_cog_raster_layer(resource: NGWRasterLayer):
    if not isinstance(resource, NGWRasterLayer):
        raise Exception("Resource type is not raster layer!")
    if not resource.is_cog:
        raise UnsupportedRasterTypeException

    connections_manager = NgwConnectionsManager()
    connection = connections_manager.connection(resource.connection_id)

    uri_config = {
        "path": f"{resource.get_absolute_vsicurl_url()}/cog",
    }
    is_fixed = False
    connection.update_uri_config(uri_config, workaround=not is_fixed)

    provider_registry = QgsProviderRegistry.instance()
    resource_uri = provider_registry.encodeUri("gdal", uri_config)

    qgs_raster_layer = QgsRasterLayer(
        resource_uri, resource.common.display_name, "gdal"
    )
    if not qgs_raster_layer.isValid():
        logger.error(
            f"Failed to add raster layer to QGIS. URL: {resource_uri}"
        )
        raise Exception(
            f'Layer "{resource.common.display_name}" can\'t be added to the map!'
        )

    return qgs_raster_layer


def _add_style_to_layer(style_resource: NGWQGISStyle, qgs_layer: QgsMapLayer):
    qml_url = style_resource.download_qml_url()
    qml_req = QNetworkRequest(QUrl(qml_url))

    connections_manager = NgwConnectionsManager()
    connection = connections_manager.connection(style_resource.connection_id)
    connection.update_network_request(qml_req)

    dwn_qml_manager = QgsNetworkAccessManager()
    reply_content = dwn_qml_manager.blockingGet(qml_req, forceRefresh=True)

    if reply_content.error():
        logger.error(f"Failed to download QML: {reply_content.errorString()}")
        return

    style = QgsMapLayerStyle(reply_content.content().data().decode())
    if not style.isValid():
        logger.error("Unable apply style to the layer")
        return

    style_manager = qgs_layer.styleManager()
    assert style_manager is not None

    style_manager.addStyle(style_resource.common.display_name, style)


def _add_all_styles_to_layer(
    qgs_layer: QgsMapLayer,
    resources: List[NGWQGISStyle],
    default_style: Optional[NGWQGISStyle] = None,
) -> None:
    styles = list(
        filter(lambda resource: isinstance(resource, NGWQGISStyle), resources)
    )
    if len(styles) == 0:
        return

    styles.sort(key=lambda resource: resource.common.display_name)

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


def add_resource_as_geojson(
    resource: NGWVectorLayer, children, default_style=None
):
    qgs_geojson_layer = _add_geojson_layer(resource)

    _add_all_styles_to_layer(qgs_geojson_layer, children, default_style)
    _add_aliases(qgs_geojson_layer, resource)
    _add_lookup_tables(qgs_geojson_layer, resource)

    qgs_geojson_layer.setCustomProperty(
        "ngw_connection_id", resource.connection_id
    )
    qgs_geojson_layer.setCustomProperty(
        "ngw_resource_id", resource.resource_id
    )

    project = QgsProject.instance()
    assert project is not None
    map_layer = project.addMapLayer(qgs_geojson_layer)
    if map_layer is None:
        raise Exception("Failed to add layer to QGIS")


def add_resource_as_cog_raster(
    resource: NGWRasterLayer, styles, default_style=None
) -> QgsRasterLayer:
    qgs_raster_layer = _add_cog_raster_layer(resource)

    _add_all_styles_to_layer(qgs_raster_layer, styles, default_style)

    qgs_raster_layer.setCustomProperty(
        "ngw_connection_id", resource.connection_id
    )
    qgs_raster_layer.setCustomProperty("ngw_resource_id", resource.resource_id)

    project = QgsProject.instance()
    assert project is not None
    map_layer = project.addMapLayer(qgs_raster_layer)
    if map_layer is None:
        raise Exception("Failed to add layer to QGIS")

    return qgs_raster_layer


def add_resource_as_wfs_layers(wfs_resource: NGWWfsService):
    if not isinstance(wfs_resource, NGWWfsService):
        raise NGWError(
            NGWError.TypeUnknownError, "Resource type is not WfsService!"
        )

    # Add group
    project = QgsProject.instance()
    assert project is not None
    toc_root = project.layerTreeRoot()
    assert toc_root is not None
    layers_group = toc_root.insertGroup(0, wfs_resource.common.display_name)

    # Add layers
    for wfs_layer in wfs_resource.wfs.layers:
        url = wfs_resource.get_wfs_url(wfs_layer.keyname)
        qgs_wfs_layer = QgsVectorLayer(url, wfs_layer.display_name, "WFS")

        ngw_vector_layer = wfs_resource.get_source_layer(wfs_layer.resource_id)

        # Add vector style. Select the first QGIS style if several.
        vec_layer_children = ngw_vector_layer.get_children()
        _add_all_styles_to_layer(qgs_wfs_layer, vec_layer_children)

        _add_aliases(qgs_wfs_layer, ngw_vector_layer)
        _add_lookup_tables(qgs_wfs_layer, ngw_vector_layer)

        qgs_wfs_layer.setCustomProperty(
            "ngw_connection_id", wfs_resource.connection_id
        )
        qgs_wfs_layer.setCustomProperty(
            "ngw_resource_id", wfs_resource.resource_id
        )

        project = QgsProject.instance()
        assert project is not None
        project.addMapLayer(qgs_wfs_layer, False)
        layers_group.insertLayer(0, qgs_wfs_layer)


def add_ogcf_resource(ogcf_resource: NGWOgcfService):
    if not isinstance(ogcf_resource, NGWOgcfService):
        raise NGWError("Resource type is not OGCService!")

    project = QgsProject.instance()
    assert project is not None
    layer_tree_root = project.layerTreeRoot()
    assert layer_tree_root is not None
    layers_group = layer_tree_root.insertGroup(
        0, ogcf_resource.common.display_name
    )
    assert layers_group is not None

    # Add layers
    for ogc_layer in ogcf_resource.ogcf.layers:
        url = ogcf_resource.get_ogcf_url(ogc_layer.keyname)
        qgis_ogc_layer = QgsVectorLayer(url, ogc_layer.display_name, "OAPIF")

        layer_resource = ogcf_resource.res_factory.get_resource(
            ogc_layer.resource_id
        )

        # # Add vector style. Select the first QGIS style if several.
        vec_layer_children = layer_resource.get_children()
        _add_all_styles_to_layer(qgis_ogc_layer, vec_layer_children)

        _add_aliases(qgis_ogc_layer, layer_resource)
        _add_lookup_tables(qgis_ogc_layer, layer_resource)

        qgis_ogc_layer.setCustomProperty(
            "ngw_connection_id", ogcf_resource.connection_id
        )
        qgis_ogc_layer.setCustomProperty(
            "ngw_resource_id", ogcf_resource.resource_id
        )

        project.addMapLayer(qgis_ogc_layer, addToLegend=False)
        layers_group.addLayer(qgis_ogc_layer)
