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
import os
import sys

ICONS_DIR = os.path.join(
    os.path.dirname(__file__).decode(sys.getfilesystemencoding()),
    'icons'
)

ngw_api_logger = None
debug = True

def setLogger(logger):
    global ngw_api_logger
    ngw_api_logger = logger


"""
Enable debuging
    in QGIS use in console:
        from nextgis_connect.ngw_api.utils import setDebugEnabled
        setDebugEnabled(True)
"""
def setDebugEnabled(flag):
    global debug
    debug = flag

def log(msg):
    if debug is False:
        return

    if ngw_api_logger is not None:
        ngw_api_logger(msg)
