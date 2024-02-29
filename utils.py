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

ICONS_DIR = os.path.join(os.path.dirname(__file__), "icons")

ngw_api_logger = None
debug = False


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


def ngw_version_parts(version):
    strs = version.split(".")
    ints = [0, 0, 0, sys.maxsize]  # sys.maxsize is present for python 2/3 both
    for i in range(4):
        if i >= len(strs):
            continue
        if strs[i].startswith("dev"):
            ints[3] = int(strs[i].replace("dev", ""))
            continue
        ints[i] = int(strs[i])
    return ints


# Note: this method does not include all PEP 440 features. Supports either
# X.Y.Z or X.Y.Z.devN (all parts are not obligatory).
def ngw_version_compare(lversion, rversion):
    try:
        lints = ngw_version_parts(lversion)
        rints = ngw_version_parts(rversion)

        for i in range(4):
            if lints[i] > rints[i]:
                return 1
            elif rints[i] > lints[i]:
                return -1
        return 0
    except Exception:
        return None
