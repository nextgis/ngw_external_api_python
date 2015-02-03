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
from qgis.core import QgsVectorLayer, QgsMapLayerRegistry, QgsMapLayer
from ngw_api.core.ngw_error import NGWError
from ngw_api.core.ngw_vector_layer import NGWVectorLayer


def add_resource_as_geojson(resource, return_extent=False):
    if not isinstance(resource, NGWVectorLayer):
        raise NGWError('Resource type is not VectorLayer!')

    qgs_geojson_layer = QgsVectorLayer(resource.get_geojson_url(), 'ogr')

    QgsMapLayerRegistry.instance().addMapLayer(qgs_geojson_layer)

    if return_extent:
        if qgs_geojson_layer.extent().isEmpty() and qgs_geojson_layer.type() == QgsMapLayer.VectorLayer:
            qgs_geojson_layer.updateExtents()
            return qgs_geojson_layer.extent()