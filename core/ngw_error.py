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


class NGWError(Exception):
    TypeUnknownError, TypeRequestError, TypeNGWError, TypeNGWUnexpectedAnswer = list(range(4))

    def __init__(self, type, message, url=None): 
        if not isinstance(message, str):
            self.message = str(message, 'utf-8')
        else:
            self.message = message

        self.type = type
        self.url = url

    def __str__(self):
        return self.message
