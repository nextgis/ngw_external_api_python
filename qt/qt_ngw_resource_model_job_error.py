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

class NGWResourceModelJobError(object):
    """Common error"""
    def __init__(self, msg, trace=None):
        super(NGWResourceModelJobError, self).__init__()
        self.msg = msg

class JobError(NGWResourceModelJobError):
	"""Specific job error"""
	def __init__(self, msg, wrapped_exception=None):
		super(JobError, self).__init__(msg)
		self.wrapped_exception = wrapped_exception

class JobInternalError(NGWResourceModelJobError):
	"""Unexpected job error. With trace"""
	def __init__(self, msg, trace):
		super(JobInternalError, self).__init__(msg, trace)
		self.trace = trace

class JobServerRequestError(NGWResourceModelJobError):
	"""Something wrong with request to NGW like  no connection, 502, ngw error """
	def __init__(self, msg, url):
		super(JobServerRequestError, self).__init__(msg)
		self.url = url

class JobNGWError(JobServerRequestError):
	"""NGW answer is received, but NGW cann't execute request for perform the job"""
	def __init__(self, msg, url):
		super(JobNGWError, self).__init__(msg, url)


class JobAuthorizationError(JobNGWError):
	"""NGW cann't execute request for perform the job because user does not have rights"""
	def __init__(self, url):
		super(JobAuthorizationError, self).__init__("", url)
