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
import os
import urllib.parse
from base64 import b64encode
from io import FileIO
from typing import Optional, Tuple

import requests
from requests.utils import to_native_string

from nextgis_connect.logging import logger

from .ngw_connection_settings import NGWConnectionSettings
from .ngw_error import NGWError

UPLOAD_FILE_URL = "/api/component/file_upload/upload"
GET_VERSION_URL = "/api/component/pyramid/pkg_version"


class File2Upload(FileIO):
    def __init__(self, path, callback):
        super().__init__(path, "rb")
        self.seek(0, os.SEEK_END)
        self._total = self.tell()
        self._readed = 0
        self.seek(0)
        self._callback = callback

    def __len__(self):
        return self._total

    def read(self, size):
        data = FileIO.read(self, size)
        self._readed += len(data)
        self._callback(self._total, self._readed)
        return data


def _basic_auth_str(username, password):
    """Returns a Basic Auth string."""

    authstr = "Basic " + to_native_string(
        b64encode((f"{username}:{password}").encode()).strip()
    )

    return authstr


class NGWConnection:
    AbilityBaseMap = list(range(1))
    __auth: Tuple[Optional[str], Optional[str]]

    def __init__(self, conn_settings: NGWConnectionSettings):
        self.__server_url = None
        self.__session = requests.Session()
        self.__auth = ("", "")
        self.__proxy = None
        self.set_from_settings(conn_settings)

        self.__ngw_components = None

    def set_from_settings(self, conn_settings: NGWConnectionSettings):
        self.server_url = conn_settings.server_url
        self.set_auth(conn_settings.username, conn_settings.password)

        if conn_settings.proxy_enable and conn_settings.proxy_host != "":
            proxy_url = conn_settings.proxy_host
            if conn_settings.proxy_port != "":
                proxy_url = "%s:%s" % (proxy_url, conn_settings.proxy_port)
            if conn_settings.proxy_user != "":
                proxy_url = f"{conn_settings.proxy_user}:{conn_settings.proxy_password}@{proxy_url}"

            self.__proxy = {"http": proxy_url}

    @property
    def server_url(self):
        return self.__server_url

    @server_url.setter
    def server_url(self, value):
        if isinstance(value, str):
            self.__server_url = value.strip().rstrip(r"\\/")
        else:
            self.__server_url = value

    def set_auth(self, username: Optional[str], password: Optional[str]):
        self.__auth = (username, password)

    def get_auth(self) -> Tuple[Optional[str], Optional[str]]:
        return self.__auth

    def __request(self, sub_url, method, params=None, **kwargs):
        payload = None
        if params:
            payload = json.dumps(params)

        if "data" in kwargs:
            payload = kwargs["data"]

        json_data = None
        if "json" in kwargs:
            json_data = kwargs["json"]

        logger.debug(
            f"\nRequest\nmethod: {method}\nurl: {urllib.parse.urljoin(self.server_url, sub_url)}\ndata: {payload}\njson:"
        )

        url = urllib.parse.urljoin(self.server_url, sub_url)
        req = requests.Request(method, url, data=payload, json=json_data)

        if all(map(len, self.__auth)):
            req.headers["Authorization"] = _basic_auth_str(
                self.__auth[0], self.__auth[1]
            )

        prep = self.__session.prepare_request(req)

        try:
            resp = self.__session.send(prep, proxies=self.__proxy)
        except requests.exceptions.ConnectionError as error:
            raise NGWError(
                NGWError.TypeRequestError, "Connection error", req.url
            ) from error
        except requests.exceptions.RequestException as error:
            logger.debug("Response error")
            raise NGWError(
                NGWError.TypeRequestError, "%s" % type(error), req.url
            ) from error

        if resp.status_code == 502:
            logger.debug("Response\nerror status_code 502")
            raise NGWError(
                NGWError.TypeRequestError,
                "Response status code is 502",
                req.url,
            )

        if resp.status_code // 100 != 2:
            logger.debug(
                f"Response\nerror status_code {resp.status_code}\nmsg: {resp.content.decode()!r}"
            )
            raise NGWError(NGWError.TypeNGWError, resp.content, req.url)

        try:
            json_response = resp.json()
        except Exception as error:
            logger.debug("Response\nerror response JSON parse")
            raise NGWError(
                NGWError.TypeNGWUnexpectedAnswer, "", req.url
            ) from error

        return json_response

    def get(self, sub_url, params=None, **kwargs):
        return self.__request(sub_url, "GET", params, **kwargs)

    def post(self, sub_url, params=None, **kwargs):
        return self.__request(sub_url, "POST", params, **kwargs)

    def put(self, sub_url, params=None, **kwargs):
        return self.__request(sub_url, "PUT", params, **kwargs)

    def patch(self, sub_url, params=None, **kwargs):
        return self.__request(sub_url, "PATCH", params, **kwargs)

    def delete(self, sub_url, params=None, **kwargs):
        return self.__request(sub_url, "DELETE", params, **kwargs)

    def get_upload_file_url(self):
        return UPLOAD_FILE_URL

    def upload_file(self, filename, callback):
        try:
            with File2Upload(filename, callback) as fd:
                upload_info = self.put(self.get_upload_file_url(), data=fd)
                return upload_info
        except requests.exceptions.RequestException as error:
            raise NGWError(
                NGWError.TypeRequestError,
                error.message.args[0],
                self.get_upload_file_url(),
            ) from error

    def download_file(self, url):
        req = requests.Request(
            "GET", urllib.parse.urljoin(self.server_url, url)
        )

        if all(map(len, self.__auth)):
            req.headers["Authorization"] = _basic_auth_str(
                self.__auth[0], self.__auth[1]
            )

        prep = self.__session.prepare_request(req)

        try:
            resp = self.__session.send(prep, stream=True)
        except requests.exceptions.RequestException as error:
            raise NGWError(
                NGWError.TypeRequestError, error.message.args[0], req.url
            ) from error

        if resp.status_code / 100 != 2:
            raise NGWError(NGWError.TypeNGWError, resp.content, req.url)

        return resp.content

    def get_ngw_components(self):
        if self.__ngw_components is None:
            try:
                self.__ngw_components = self.get(GET_VERSION_URL)
            except requests.exceptions.RequestException:
                self.__ngw_components = {}

        return self.__ngw_components

    def get_version(self):
        ngw_components = self.get_ngw_components()
        return ngw_components.get("nextgisweb")

    def get_abilities(self):
        ngw_components = self.get_ngw_components()
        abilities = []
        if "nextgisweb_basemap" in ngw_components:
            abilities.append(self.AbilityBaseMap)

        return abilities
