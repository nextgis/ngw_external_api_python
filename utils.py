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
            if rints[i] > lints[i]:
                return -1

    except Exception:
        return None
    else:
        return 0
