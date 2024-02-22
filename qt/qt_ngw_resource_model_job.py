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
import json
import re
import sys
import traceback
from typing import List, Union

from qgis.PyQt.QtCore import (
    QObject, pyqtSignal
)

from ..core.ngw_error import NGWError
from ..core.ngw_resource import NGWResource
from ..core.ngw_vector_layer import NGWVectorLayer
from ..core.ngw_group_resource import NGWGroupResource
from ..core.ngw_resource_creator import ResourceCreator
from ..core.ngw_resource_factory import NGWResourceFactory
from ..core.ngw_webmap import NGWWebMap, NGWWebMapLayer, NGWWebMapRoot

from ..qgis.qgis_ngw_connection import QgsNgwConnection

from ..utils import log

from .qt_ngw_resource_model_job_error import (
    JobNGWError, JobAuthorizationError, NGWResourceModelJobError, JobInternalError,
    JobServerRequestError
)


class NGWResourceModelJobResult:
    added_resources: List[NGWResource]
    deleted_resources: List[NGWResource]
    edited_resources: List[NGWResource]
    main_resource_id: int

    def __init__(self):
        self.added_resources = []
        self.deleted_resources = []
        self.edited_resources = []

        self.main_resource_id = -1

    def putAddedResource(
        self, ngw_resource: NGWResource, is_main: bool = False
    ) -> None:
        self.added_resources.append(ngw_resource)
        if is_main:
            self.main_resource_id = ngw_resource.common.id

    def putEditedResource(
        self, ngw_resource: NGWResource, is_main: bool = False
    ) -> None:
        self.edited_resources.append(ngw_resource)
        if is_main:
            self.main_resource_id = ngw_resource.common.id

    def putDeletedResource(self, ngw_resource: NGWResource) -> None:
        self.deleted_resources.append(ngw_resource)

    def is_empty(self):
        return (
            len(self.added_resources) == 0
            and len(self.edited_resources) == 0
            and len(self.deleted_resources) == 0
        )


class NGWResourceModelJob(QObject):
    started = pyqtSignal()
    statusChanged = pyqtSignal(str)
    warningOccurred = pyqtSignal(object)
    errorOccurred = pyqtSignal(object)
    dataReceived = pyqtSignal(object)
    finished = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.id = self.__class__.__name__

        self.result = NGWResourceModelJobResult()

    def generate_unique_name(self, name, present_names):
        if name not in present_names:
            return name

        if re.search(r'\(\d\)$', name):
            name = name[:-3]
        new_name = name
        new_name_with_space = None
        id = 1
        while (
            new_name in present_names or new_name_with_space in present_names
        ):
            new_name = f'{name}({id})'
            new_name_with_space = f'{name} ({id})'
            id += 1
        return new_name if new_name_with_space is None else new_name_with_space

    def unique_resource_name(self, resource_name, ngw_group):
        chd_names = [ch.common.display_name for ch in ngw_group.get_children()]
        unique_resource_name = self.generate_unique_name(
            resource_name, chd_names
        )
        return unique_resource_name

    def getResourcesChain2Root(self, ngw_resource):
        ngw_resource.update()
        chain = [ngw_resource]
        parent = ngw_resource.get_parent()
        while parent is not None:
            parent.update()
            chain.insert(0, parent)
            parent = parent.get_parent()

        return chain

    def putAddedResourceToResult(
        self, ngw_resource: NGWResource, is_main: bool = False
    ):
        self.result.putAddedResource(ngw_resource, is_main)

    def putEditedResourceToResult(
        self, ngw_resource: NGWResource, is_main: bool = False
    ):
        self.result.putEditedResource(ngw_resource, is_main)

    def putDeletedResourceToResult(self, ngw_resource: NGWResource):
        self.result.putDeletedResource(ngw_resource)

    def run(self):
        self.started.emit()
        try:
            self._do()
        except NGWError as e:
            if e.type == NGWError.TypeNGWError:
                ngw_exeption_dict = json.loads(e.message)
                if ngw_exeption_dict.get("status_code") == 403:
                    self.errorOccurred.emit(JobAuthorizationError(e.url))
                elif ngw_exeption_dict.get("status_code") == 401:
                    self.errorOccurred.emit(JobAuthorizationError(e.url))
                else:
                    self.errorOccurred.emit(JobNGWError(
                        str(ngw_exeption_dict.get("message", "No message")),
                        e.url
                    ))

            elif e.type == NGWError.TypeRequestError:
                self.errorOccurred.emit(JobServerRequestError(
                    self.tr("Bad http comunication.") + str(e),
                    e.url,
                    e.user_msg,
                    e.need_reconnect
                ))

            elif e.type == NGWError.TypeNGWUnexpectedAnswer:
                self.errorOccurred.emit(JobNGWError(
                    self.tr("Can't parse server answer"), e.url
                ))

            else:
                self.errorOccurred.emit(JobServerRequestError(
                    self.tr("Something wrong with request to server"), e.url
                ))

        except NGWResourceModelJobError as e:
            self.errorOccurred.emit(e)

        except Exception as e:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            extracted_list = traceback.extract_tb(exc_traceback)
            extracted_list = [
                (f.split("\\")[-1], l, func, text)
                for f, l, func, text in extracted_list
            ]
            log('ERROR: \n{}'.format(traceback.format_exc()))
            self.errorOccurred.emit(JobInternalError(
                str(e), traceback.format_list(extracted_list)
            ))

        self.dataReceived.emit(self.result)
        self.finished.emit()

    def _do(self):
        pass


class NGWRootResourcesLoader(NGWResourceModelJob):
    ngw_connection: QgsNgwConnection

    def __init__(self, ngw_connection: QgsNgwConnection):
        super().__init__()
        self.ngw_connection = ngw_connection

    def _do(self):
        rsc_factory = NGWResourceFactory(self.ngw_connection)

        ngw_root_resource = rsc_factory.get_root_resource()
        self.putAddedResourceToResult(ngw_root_resource, is_main=True)


class NGWResourceUpdater(NGWResourceModelJob):
    def __init__(
        self,
        ngw_resources: Union[NGWResource, List[NGWResource]],
        *,
        recursive: bool = False
    ) -> None:
        super().__init__()
        if isinstance(ngw_resources, list):
            self.ngw_resources = ngw_resources
        else:
            self.ngw_resources = [ngw_resources]
            self.result.main_resource_id = ngw_resources.common.id
        self.recursive = recursive

    def _do(self):
        for ngw_resource in self.ngw_resources:
            self.__get_children(ngw_resource)

    def __get_children(self, ngw_resource: NGWResource):
        ngw_resource_children = ngw_resource.get_children()
        for ngw_resource_child in ngw_resource_children:
            self.putAddedResourceToResult(ngw_resource_child)
            if (
                self.recursive
                and isinstance(ngw_resource_child, NGWGroupResource)
            ):
                self.__get_children(ngw_resource_child)


class NGWGroupCreater(NGWResourceModelJob):
    new_group_name: str

    def __init__(self, new_group_name, ngw_resource_parent):
        super().__init__()
        self.new_group_name = new_group_name
        self.ngw_resource_parent = ngw_resource_parent

    def _do(self):
        new_group_name = self.unique_resource_name(
            self.new_group_name, self.ngw_resource_parent
        )

        ngw_group_resource = ResourceCreator.create_group(
            self.ngw_resource_parent, new_group_name
        )

        self.putAddedResourceToResult(ngw_group_resource, is_main=True)
        self.ngw_resource_parent.update()


class NGWResourceDelete(NGWResourceModelJob):
    def __init__(self, ngw_resource):
        NGWResourceModelJob.__init__(self)
        self.ngw_resource = ngw_resource

    def _do(self):
        NGWResource.delete_resource(self.ngw_resource)

        self.putDeletedResourceToResult(self.ngw_resource)


class NGWCreateWfsOrOgcfService(NGWResourceModelJob):
    def __init__(
        self,
        service_type: str,
        ngw_vector_layer: NGWVectorLayer,
        ngw_group_resource: NGWGroupResource,
        max_features: int
    ):
        super().__init__()
        assert service_type in ('WFS', 'OGC API - Features')
        self.service_type = service_type
        self.ngw_vector_layer = ngw_vector_layer
        self.ngw_group_resource = ngw_group_resource
        self.ret_obj_num = max_features

    def _do(self):
        service_name: str = self.ngw_vector_layer.common.display_name
        service_name += f' — {self.service_type} service'
        ngw_wfs_service_name = self.unique_resource_name(
            service_name,
            self.ngw_group_resource
        )

        service_resource = ResourceCreator.create_wfs_or_ogcf_service(
            self.service_type,
            ngw_wfs_service_name,
            self.ngw_group_resource,
            [self.ngw_vector_layer],
            self.ret_obj_num
        )

        self.putAddedResourceToResult(service_resource, is_main=True)


class NGWCreateWfsService(NGWCreateWfsOrOgcfService):
    def __init__(
        self,
        ngw_vector_layer: NGWVectorLayer,
        ngw_group_resource: NGWGroupResource,
        max_features: int
    ):
        super().__init__(
            'WFS', ngw_vector_layer, ngw_group_resource, max_features
        )


class NGWCreateOgcfService(NGWCreateWfsOrOgcfService):
    def __init__(
        self,
        ngw_vector_layer: NGWVectorLayer,
        ngw_group_resource: NGWGroupResource,
        max_features: int
    ):
        super().__init__(
            'OGC API - Features', ngw_vector_layer, ngw_group_resource, max_features
        )


class NGWCreateMapForStyle(NGWResourceModelJob):
    def __init__(self, ngw_style):
        NGWResourceModelJob.__init__(self)
        self.ngw_style = ngw_style

    def _do(self):
        ngw_layer = self.ngw_style.get_parent()
        ngw_group = ngw_layer.get_parent()

        ngw_map_name = self.unique_resource_name(
            self.ngw_style.common.display_name + "-map",
            ngw_group
        )

        ngw_webmap_root_group = NGWWebMapRoot()
        ngw_webmap_root_group.appendChild(
            NGWWebMapLayer(
                self.ngw_style.common.id,
                ngw_layer.common.display_name,
                True,
                None,
                legend=True
            )
        )

        ngw_resource = NGWWebMap.create_in_group(
            ngw_map_name,
            ngw_group,
            [item.toDict() for item in ngw_webmap_root_group.children],
            bbox=ngw_layer.extent()
        )

        self.putAddedResourceToResult(ngw_resource, is_main=True)


class NGWRenameResource(NGWResourceModelJob):
    def __init__(self, ngw_resource, new_name):
        NGWResourceModelJob.__init__(self)
        self.ngw_resource = ngw_resource
        self.new_name = new_name

    def _do(self):
        self.ngw_resource.change_name(self.new_name)

        # self.putAddedResourceToResult(self.ngw_resource, is_main=True)
        self.putEditedResourceToResult(self.ngw_resource, is_main=True)
