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
from PyQt4.QtCore import Qt
from .qt_ngw_resource_item import QNGWResourceItem


class QNGWFakeRootItem():
    """
    Fake item for show real NGW root element in tree
    """

    def __init__(self, ngw_root_resource, parent):
        self._ngw_resource = None
        self._parent = parent
        self._children = [QNGWResourceItem(ngw_root_resource, self)]

    def parent(self):
        return self._parent

    def row(self):
        if self._parent:
            return self._parent.get_children().index(self)
        else:
            return 0

    def get_children(self):
        return self._children

    def get_child(self, row):
        return self._children[row]

    def get_children_count(self):
        return len(self._children)

    def has_children(self):
        return True

    def data(self, role):
        if role == Qt.DisplayRole:
            return 'FakeRoot'