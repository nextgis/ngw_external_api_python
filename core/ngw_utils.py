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

import re, traceback

from .ngw_connection_settings import NGWConnectionSettings
from .ngw_connection import NGWConnection
from .ngw_resource_factory import NGWResourceFactory
from .ngw_resource import NGWResource
from .ngw_vector_layer import NGWVectorLayer

from .ngw_error import NGWError

from ..utils import log

from ..compat_py import urlparse, parse_qs


# TODO: move to Identify plus
def ngw_resource_from_qgs_map_layer(qgs_map_layer):
    layerSource = qgs_map_layer.source()
    if 'vsicurl' in layerSource:
        layerSource = layerSource.lstrip('/vsicurl/')

    o = urlparse(layerSource)

    m = re.search(r'^.*/resource/\d+/',o.path)
    if m is None:
        return None

    # o.path is '.../resource/<resource id>/.......'
    # m.group() is '.../resource/<resource id>/'
    basePathStructure = m.group().strip('/').split('/')

    baseURL = o.scheme + '://' + o.netloc.split('@')[-1] + '/' + '/'.join(basePathStructure[:-3])
    ngw_resources_id = int(basePathStructure[-1])
    requestAttrs = parse_qs(o.query)

    ngw_username = None
    ngw_password = None

    if qgs_map_layer.providerType() == 'WFS':
        if 'username' in requestAttrs:
            ngw_username = requestAttrs.get('username')[0]
        if 'password' in requestAttrs:
            ngw_password = requestAttrs.get('password')[0]
    elif qgs_map_layer.providerType() == 'ogr':
        if o.netloc.find('@') != -1:
            auth_data = o.netloc.split('@')[0]
            ngw_username = auth_data.split(':')[0]
            ngw_password = auth_data.split(':')[1]

    else:

        return None
    #additionAttrs = {}
    #if requestAttrs.get(u'TYPENAME') is not None:
    #    additionAttrs.update({u'LayerName': requestAttrs[u'TYPENAME'][0]})
    layer_name = ""
    if requestAttrs.get('TYPENAME') is not None:
        layer_name = requestAttrs['TYPENAME'][0]
    #additionAttrs.update({u'auth':(ngw_username, ngw_password)})
    #additionAttrs.update({u'baseURL':baseURL})
    #additionAttrs.update({u'resourceId':ngw_resources_id})

    ngwConnectionSettings = NGWConnectionSettings("ngw", baseURL, ngw_username, ngw_password)
    ngwConnection = NGWConnection(ngwConnectionSettings)

    ngwResourceFactory = NGWResourceFactory(ngwConnection)

    try:
        ngw_resource = ngwResourceFactory.get_resource(ngw_resources_id)

        if ngw_resource is None:
            return None

        if ngw_resource.type_id == 'wfsserver_service':
            layers = ngw_resource.get_layers()
            for layer in layers:
                if layer["keyname"] == layer_name:
                    ngw_resources_id = layer["resource_id"]
                    break
            return ngwResourceFactory.get_resource(ngw_resources_id)
        else:
            return ngw_resource
        #return NGWVectorLayer(ngwResourceFactory, NGWResource.receive_resource_obj(ngwConnection, ngw_resources_id))
    except NGWError as e:
        return None