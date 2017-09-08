import json
from base64 import b64encode

from PyQt4.QtCore import *
from PyQt4.QtNetwork import *

from qgis.core import *
from qgis.utils import iface

from ..core.ngw_error import NGWError

from ..utils import log


UPLOAD_FILE_URL = '/api/component/file_upload/upload'
GET_VERSION_URL = '/api/component/pyramid/pkg_version'

class QgsNgwConnection(QObject):

    AbilityBaseMap = range(1)

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

        log(
            "Request\nmethod: {}\nurl: {}\njson({}): {}\nfile: {}".format(
                method,
                self.server_url + sub_url,
                type(json_data),
                json_data,
                file
            )
        )

        req = QNetworkRequest(QUrl(self.server_url + sub_url))

        authstr = (u'%s:%s' % self.__auth).encode('utf-8')        
        authstr = QByteArray('Basic ' +  QByteArray(authstr).toBase64())
        req.setRawHeader("Authorization", authstr);

        data = QBuffer(QByteArray())
        if file is not None:
            data = QFile(file)
        elif json_data is not None:
            req.setHeader(QNetworkRequest.ContentTypeHeader, "application/json");
            json_data = QByteArray(json_data)
            data = QBuffer(json_data)
            
        data.open(QIODevice.ReadOnly)

        loop = QEventLoop(self)
        nam = QgsNetworkAccessManager.instance()

        if method == "GET":
            rep = nam.get(req)
        elif method == "POST":
            rep = nam.post(req, data)
        elif method == "DELETE":
            rep = nam.deleteResource(req)
        else:            
            rep = nam.sendCustomRequest(req, method, data)
        
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
        if rep.error() > 0 and rep.error() < 10:
            log( "Connection error qt code: {}".format(rep.error()) )
            raise NGWError(NGWError.TypeRequestError, "Connection error qt code: {}".format(rep.error()), req.url().toString())

        status_code = rep.attribute( QNetworkRequest.HttpStatusCodeAttribute )
        if  status_code / 100 != 2:
            log("Response\nerror status_code {}\nmsg: {}".format(status_code, data))
            raise NGWError(NGWError.TypeNGWError, data, req.url().toString())

        if  status_code == 502:
            log( "Response\nerror status_code 502" )
            raise NGWError(NGWError.TypeRequestError, "Response status code is 502", req.url().toString())

        try:
            json_response = json.loads(unicode(data))
        except:
            log("Response\nerror response JSON parse")
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
        log("Download %d from %s" % (sent, total,))
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
        if ngw_components.has_key("nextgisweb_basemap"):
            abilities.append(self.AbilityBaseMap)

        return abilities
