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
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QTreeWidgetItem

from ..core.ngw_group_resource import NGWGroupResource
from ..core.ngw_qgis_vector_style import NGWQGISVectorStyle
from ..core.ngw_mapserver_style import NGWMapServerStyle


class QNGWItem(QTreeWidgetItem):
    def __init__(self):
        QTreeWidgetItem.__init__(self)
        
        self.locked_item = QTreeWidgetItem(["loading..."])
        self.locked_item.setFlags(Qt.NoItemFlags)
        self.locked_item.setDisabled(True)

        self.release()

    def lock(self):
        self.__isLock = True
        self.setFlags(Qt.NoItemFlags)

        self.addChild(
            self.locked_item
        )

    def is_locked(self):
        return self.__isLock

    def release(self):
        self.__isLock = False
        self.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)

        self.removeChild(
            self.locked_item
        )

    def ngw_resource_children_count(self):
        raise NotImplementedError()


class QNGWConnectionItem(QNGWItem):
    def __init__(self, ngw_connection_settings=None):
        QNGWItem.__init__(self)

        self.__has_connection = ngw_connection_settings is not None
        if self.__has_connection:
            title = ngw_connection_settings.connection_name
        else:
            title = "no connection"

    def ngw_resource_children_count(self):
        return self.__has_connection


class QNGWResourceItem(QNGWItem):
    NGWResourceRole = Qt.UserRole
    NGWResourceIdRole = Qt.UserRole + 1

    def __init__(self, ngw_resource):
        QNGWItem.__init__(self)

        self.setText(0, self.title(ngw_resource))
        self.setIcon(0, QIcon(ngw_resource.icon_path))
        self.setData(0, self.NGWResourceRole, ngw_resource)
        self.setData(0, self.NGWResourceIdRole, ngw_resource.common.id)

    def title(self, ngw_resource):       
        title = ngw_resource.common.display_name
        
        if ngw_resource.type_id == NGWQGISVectorStyle.type_id:
            title = "(qgis) " + title
        if ngw_resource.type_id == NGWMapServerStyle.type_id:
            title = "(ms) " + title

        return title


    def ngw_resource_id(self):
        return self.data(0, self.NGWResourceIdRole)

    def ngw_resource_children_count(self):
        ngw_resource = self.data(0, self.NGWResourceRole)
        if ngw_resource.common.children > 0:
            if ngw_resource.children_count is not None:
                return ngw_resource.children_count
        return ngw_resource.common.children

    def is_group(self):
        ngw_resource = self.data(0, self.NGWResourceRole)
        return ngw_resource.type_id == NGWGroupResource.type_id

    def more_priority(self, item):
        if not isinstance(item, QNGWItem):
            return True

        if isinstance(item, QNGWConnectionItem):
            return True

        if self.is_group() != item.is_group():
            return self.is_group() > item.is_group()

        return self.text(0).lower() < item.text(0).lower()
