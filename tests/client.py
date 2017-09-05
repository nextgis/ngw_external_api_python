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

from ngw_api.core.ngw_error import NGWError

from ngw_api import utils


ngwConnectionSettings = None
ngwConnection = None
ngwResourceFactory = None


def connect(connection_string=None):
	url = None
	user = ""
	pwd = ""
	
	if connection_string is not None:
		url, userpwd = connection_string.split("@")
		user, pwd = userpwd.split(":")

	url = raw_input("Url: ") if url is None else url
	user = raw_input("User: ") if user is None else user

	if user != "":
		pwd = raw_input("Password: ") if pwd is None else pwd		
	else:
		pwd = ""

	global ngwConnectionSettings
	ngwConnectionSettings = NGWConnectionSettings("ngw", url, user, pwd)
	global ngwConnection
	ngwConnection = NGWConnection(ngwConnectionSettings)
	global ngwResourceFactory
	ngwResourceFactory = NGWResourceFactory(ngwConnectionSettings)


def reconnect():
	connect()

def clinet_print(msg):
	print msg

def enable_logging():
	utils.debug = True
	utils.setLogger(clinet_print)

def ngw_client_request(fn):
	def wrapped(*args, **wargs):
		if ngwConnection is None:
			print "Need establish connection!"
			connect()
		try:
			return fn(*args, **wargs)
		except NGWError as err:
			if err.type == NGWError.TypeNGWError:
				ngw_exeption_dict = json.loads(err.message)
				print "NGW Error: %s" % ngw_exeption_dict.get("message", "No message") 
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
	print "parent_ngw_resource: ", parent_ngw_resource

	#ToDO check resource type

	ngw_wms_connection = NGWWmsConnection.create_in_group(name, parent_ngw_resource, url)
	print "ngw_wms_connection: ", ngw_wms_connection
	return ngw_wms_connection