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
from base64 import b64encode

from osgeo import gdal

from qgis.PyQt.QtCore import *
from qgis.PyQt.QtNetwork import *

from qgis.core import *
from qgis.utils import iface

from ..core.ngw_error import NGWError

from ..utils import log

from ..compat_py import CompatPy
from .compat_qgis import CompatQt


UPLOAD_FILE_URL = '/api/component/file_upload/upload'
GET_VERSION_URL = '/api/component/pyramid/pkg_version'

class QgsNgwConnection(QObject):

    AbilityBaseMap = list(range(1))


    """docstring for QgsNgwConnection"""
    def __init__(self, conn_settings, parent):
        super(QgsNgwConnection, self).__init__(parent)

        self.__server_url = None
        self.__auth = ("", "")
        self.set_from_settings(conn_settings)

        self.__ngw_components = None


    def set_from_settings(self, conn_settings):
        self.server_url = conn_settings.server_url
        self.set_auth(conn_settings.username, conn_settings.password)


    def set_auth(self, username, password):
        self.__auth = (username, password)

    def get_auth(self):
        return self.__auth


    def get(self, sub_url, params=None, **kwargs):
        return self.__request(sub_url, 'GET', params, **kwargs)

    def post(self, sub_url, params=None, **kwargs):
        return self.__request(sub_url, 'POST', params, **kwargs)

    def put(self, sub_url, params=None, **kwargs):
        return self.__request(sub_url, 'PUT', params, **kwargs)

    def patch(self, sub_url, params=None, **kwargs):
        return self.__request(sub_url, 'PATCH', params, **kwargs)

    def delete(self, sub_url, params=None, **kwargs):
        return self.__request(sub_url, 'DELETE', params, **kwargs)


    def __request(self, sub_url, method, params=None, **kwargs):
        json_data = None
        if params:
            json_data = json.dumps(params)

        file = kwargs.get("file")

        url = self.server_url + sub_url

        log(
            "Request\nmethod: {}\nurl: {}\njson({}): {}\nfile: {}".format(
                method,
                url,
                type(json_data),
                json_data,
                file
            )
        )

        req = QNetworkRequest(QUrl(url))

        gdal.SetConfigOption('GDAL_HTTP_USERPWD', '') # clear old creds

        if all(map(len, self.__auth)):
            authstr = ('%s:%s' % self.__auth).encode('utf-8')
            authstr = QByteArray(authstr).toBase64()
            authstr = QByteArray(('Basic ').encode('utf-8')).append(authstr)
            req.setRawHeader(("Authorization").encode('utf-8'), authstr)

            gdal.SetConfigOption('GDAL_HTTP_USERPWD', '{}:{}'.format(self.__auth[0], self.__auth[1]))

        data = QBuffer(QByteArray())
        if file is not None:
            data = QFile(file)
        elif json_data is not None:
            req.setHeader(QNetworkRequest.ContentTypeHeader, "application/json");
            json_data = QByteArray(json_data.encode('utf-8'))
            data = QBuffer(json_data)

        data.open(QIODevice.ReadOnly)

        loop = QEventLoop(self)
        nam = QgsNetworkAccessManager.instance()

        has_redirect_policy = False
        if CompatQt.has_redirect_policy():
            nam.setRedirectPolicy(QNetworkRequest.NoLessSafeRedirectPolicy)
            has_redirect_policy = True

        if method == "GET":
            rep = nam.get(req)
        elif method == "POST":
            rep = nam.post(req, data)
        elif method == "DELETE":
            rep = nam.deleteResource(req)
        else:
            rep = nam.sendCustomRequest(req, method.encode('utf-8'), data)

        rep.finished.connect(loop.quit)
        if file is not None:
            rep.uploadProgress.connect(self.sendUploadProgress)

        loop.exec_()
        rep.finished.disconnect(loop.quit)

        data.close()
        data = rep.readAll()

        # try:
        #     resp = self.__session.send(prep, proxies=self.__proxy)
        # except requests.exceptions.ConnectionError:
        #     raise NGWError(NGWError.TypeRequestError, "Connection error", req.url)
        # except requests.exceptions.RequestException as e:
        #     log( "Response\nerror {}: {}".format(type(e), e) )
        #     raise NGWError(NGWError.TypeRequestError, "%s" % type(e), req.url)

        # if resp.status_code == 502:
        #     log( "Response\nerror status_code 502" )
        #     raise NGWError(NGWError.TypeRequestError, "Response status code is 502", req.url)

        # if resp.status_code / 100 != 2:
        #     log("Response\nerror status_code {}\nmsg: {}".format(resp.status_code, resp.content))
        #     raise NGWError(NGWError.TypeNGWError, resp.content, req.url)

        # try:
        #     json_response = resp.json()
        # except:
        #     log("Response\nerror response JSON parse")
        #     raise NGWError(NGWError.TypeNGWUnexpectedAnswer, "", req.url)

        # Indicate that request has been timed out by QGIS.
        # TODO: maybe use QgsNetworkAccessManager::requestTimedOut()?
        if rep.error() == 5:
            log('Connection error qt code: 5 (QNetworkReply::OperationCanceledError)')
            raise NGWError(NGWError.TypeRequestError, 'Connection has been aborted or closed', req.url().toString(),
                self.tr('Сonnection closed by QGIS. Increase timeout (Settings -> Options -> Network) to 300000 and retry uploading'))

        if rep.error() > 0 and rep.error() < 10:
            log( "Connection error qt code: {}".format(rep.error()) )
            raise NGWError(NGWError.TypeRequestError, "Connection error qt code: {}".format(rep.error()), req.url().toString())

        status_code = rep.attribute( QNetworkRequest.HttpStatusCodeAttribute )

        rep_str = CompatPy.decode_reply_escape(data)

        #if  status_code / 100 != 2:
        if int(str(status_code)[:1]) != 2:
            log("Response\nerror status_code {}\nmsg: {}".format(status_code, rep_str))

            ngw_message_present = False
            try:
                json.loads(bytes(data).decode())
                ngw_message_present = True
            except Exception as e:
                pass

            if ngw_message_present:
                raise NGWError(NGWError.TypeNGWError, rep_str, req.url().toString())
            else:
                raise NGWError(NGWError.TypeRequestError, "Response status code is %s" % status_code, req.url().toString())

        try:
            json_response = json.loads(bytes(data).decode())
        except:
            log("Response\nerror response JSON parse\n%s" % rep_str)
            raise NGWError(NGWError.TypeNGWUnexpectedAnswer, "", req.url().toString())

        rep.deleteLater()
        del rep
        loop.deleteLater()
        del loop

        return json_response


    def get_upload_file_url(self):
        return UPLOAD_FILE_URL


    def upload_file(self, filename, callback):
        self.uploadProgressCallback = callback
        return self.put(self.get_upload_file_url(), file=filename)


    def sendUploadProgress(self, sent, total):
        log("Upload %d from %s" % (sent, total,))
        # For Qt 5 the uploadProgress signal is sometimes emited when
        # sent and total are 0.
        # TODO: understand why. For now prevent calling uploadProgressCallback()
        # so not to allow zero devision in according callbacks.
        if sent != 0 and total != 0:
            self.uploadProgressCallback(total, sent)


    def get_ngw_components(self):
        if self.__ngw_components is None:
            self.__ngw_components = self.get(GET_VERSION_URL)
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



