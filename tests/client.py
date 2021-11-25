# -*- coding: utf-8 -*-
"""
Simple ngw client

Usage:

from ngw_api.tests import client
reload(client)
client.connect()
client.enable_logging()
ngw_root_group = client.get_resource(0)

"""

import os
import sys
import json

from ngw_api.core.ngw_connection_settings import NGWConnectionSettings
from ngw_api.core.ngw_connection import NGWConnection
from ngw_api.core.ngw_resource_factory import NGWResourceFactory
from ngw_api.core.ngw_resource import NGWResource
from ngw_api.core.ngw_vector_layer import NGWVectorLayer
from ngw_api.core.ngw_feature import NGWFeature
from ngw_api.core.ngw_attachment import NGWAttachment
from ngw_api.core.ngw_wms_connection import NGWWmsConnection
from ngw_api.core.ngw_resource_creator import ResourceCreator
from ngw_api.core.ngw_webmap import *

from ngw_api.core.ngw_error import NGWError

from ngw_api import utils


try: # for python 2 try to rebind
    input = raw_input
except NameError:
    pass


ngwConnectionSettings = None
ngwConnection = None
ngwResourceFactory = None


def connect(connection_string=None):
    url = None
    user = None
    pwd = None

    if connection_string is not None:
        url, userpwd = connection_string.split("@")
        user, pwd = userpwd.split(":")

    url = input("Url: ") if url is None else url
    user = input("User: ") if user is None else user

    if user != "":
        pwd = input("Password: ") if pwd is None else pwd
    else:
        pwd = ""

    global ngwConnectionSettings
    ngwConnectionSettings = NGWConnectionSettings("ngw", url, user, pwd)
    global ngwConnection
    ngwConnection = NGWConnection(ngwConnectionSettings)
    global ngwResourceFactory
    ngwResourceFactory = NGWResourceFactory(ngwConnection)


def reconnect():
    connect()

def clinet_print(msg):
    print(msg)

def enable_logging():
    utils.debug = True
    utils.setLogger(clinet_print)

def ngw_client_request(fn):
    def wrapped(*args, **wargs):
        if ngwConnection is None:
            print("Need establish connection!")
            connect()
        try:
            return fn(*args, **wargs)
        except NGWError as err:
            if err.type == NGWError.TypeNGWError:
                ngw_exeption_dict = json.loads(err.message)
                print("NGW Error: %s" % ngw_exeption_dict.get("message", "No message"))
                return None

            raise err


    return wrapped

@ngw_client_request
def get_ngw_version():
    return ngwConnection.get_version()

@ngw_client_request
def get_resource(ngw_resource_id):
    """
    Get ngw resource by id
    """
    return ngwResourceFactory.get_resource(ngw_resource_id)


@ngw_client_request
def create_wms(name, url, parent_ngw_resource_id):
    parent_ngw_resource = get_resource(parent_ngw_resource_id)
    print("parent_ngw_resource: %s" % str(parent_ngw_resource))

    #ToDO check resource type

    ngw_wms_connection = NGWWmsConnection.create_in_group(name, parent_ngw_resource, url)
    print("ngw_wms_connection: %s" % str(ngw_wms_connection))
    return ngw_wms_connection


@ngw_client_request
def create_raster(name, file, parent_ngw_resource):
    def uploadFileCallback(total_size, readed_size):
        print("%s - Upload (%d%%)" % (
                file,
                readed_size * 100 / total_size
            ))

    ngw_raster_layer = ResourceCreator.create_raster_layer(
        parent_ngw_resource,
        file,
        name,
        False,
        uploadFileCallback
    )

    return ngw_raster_layer


@ngw_client_request
def create_default_raster_style(ngw_raster_layer):
    return ngw_raster_layer.create_style()


@ngw_client_request
def map_for_style(name, ngw_resource_style, parent_ngw_resource, bbox=[-180, 180, 90, -90]):
    root_item = NGWWebMapRoot()
    root_item.appendChild(NGWWebMapLayer(
        ngw_resource_style.common.id,
        ngw_resource_style.common.display_name,
        True,
        0
    ))

    ngw_webmap_items_as_dicts = [item.toDict() for item in root_item.children]

    return NGWWebMap.create_in_group(name, parent_ngw_resource, ngw_webmap_items_as_dicts, bbox=bbox)
