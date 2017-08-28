import json
from base64 import b64encode

from PyQt4.QtCore import *
from PyQt4.QtNetwork import *

from qgis.core import *
from qgis.utils import iface

from ..core.ngw_error import NGWError

from ..utils import log


UPLOAD_FILE_URL = '/api/component/file_upload/upload'


def _basic_auth_str(username, password):
    """Returns a Basic Auth string."""

    authstr = QByteArray('Basic ' +  QByteArray((u'%s:%s' % (username, password)).encode('utf-8')).toBase64())

    return authstr

class QgsNgwConnection(object):
    """docstring for QgsNgwConnection"""
    def __init__(self, conn_settings):
        super(QgsNgwConnection, self).__init__()
        
        self.__server_url = None
        self.__auth = ("", "")
        self.set_from_settings(conn_settings)

        # QgsNetworkAccessManager.instance().authenticationRequired.connect(self.set_auth_to_reply)
        # self.nam = QgsNetworkAccessManager.instance()
        self.nam = QNetworkAccessManager(iface.mainWindow())
        self.loop = QEventLoop(iface.mainWindow())
        self.nam.finished.connect(self.loop.quit)

    def set_from_settings(self, conn_settings):
        self.server_url = conn_settings.server_url
        self.set_auth(conn_settings.username, conn_settings.password)

    def set_auth(self, username, password):
        self.__auth = (username, password)

    # def set_auth_to_reply(self, reply, authenticator):
    #     log(">>> set_auth_to_reply")
    #     authenticator.setUser(self.__auth[0])
    #     authenticator.setPassword(self.__auth[0])

    def get(self, sub_url, params=None, **kwargs):
        return self.__request(sub_url, 'GET', params, **kwargs)

    def post(self, sub_url, params=None, **kwargs):
        return self.__request(sub_url, 'POST', params, **kwargs)

    def put(self, sub_url, params=None, **kwargs):
        return self.__request(sub_url, 'PUT', params, **kwargs)


    def __request(self, sub_url, method, params=None, **kwargs):
        json_data = None
        if params:
            json_data = json.dumps(params)

        # if 'data' in kwargs:
        #     json_data = kwargs['data']

        # json_data = None
        # if 'json' in kwargs:
        #     json_data = kwargs['json']

        file = kwargs.get("file")

        log(
            "Request\nmethod: {}\nurl: {}\njson: {}\nfile: {}".format(
                method,
                self.server_url + sub_url,
                json_data,
                file
            )
        )

        data = None

        req = QNetworkRequest(QUrl(self.server_url + sub_url))
        # req.setAttribute(QNetworkRequest.AuthenticationReuseAttribute, _basic_auth_str(self.__auth[0], self.__auth[1]));

        if file is not None:
            data = QFile(file)
            data.open(QFile.ReadOnly)
        elif json_data is not None:
            req.setHeader(QNetworkRequest.ContentTypeHeader, "application/json");
            data = QBuffer(QByteArray(json_data))



        rep = self.nam.sendCustomRequest(req, method, data)
        # rep.finished.connect(loop.quit)
        if file is not None:
            rep.uploadProgress.connect(self.sendUploadProgress)
        
        self.loop.exec_()
        # self.nam.finished.connect(loop.quit)
        # self.nam.finished.disconnect(loop.quit)

        if isinstance(data, QFile):
            data.close()

        data = rep.readAll()
        rep.deleteLater()
        log(">>> data: %s" % type(data))
        log(">>> data: %s" % data)

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

        status_code = rep.attribute( QNetworkRequest.HttpStatusCodeAttribute )
        if  status_code / 100 != 2:
            log("Response\nerror status_code {}\nmsg: {}".format(status_code, data))
            raise NGWError(NGWError.TypeNGWError, data, req.url().toString())

        try:
            json_response = json.loads(unicode(data))
        except:
            log("Response\nerror response JSON parse")
            raise NGWError(NGWError.TypeNGWUnexpectedAnswer, "", req.url().toString())

        return json_response

    def get_upload_file_url(self):
        return UPLOAD_FILE_URL

    def upload_file(self, filename, callback):
        self.uploadProgressCallback = callback
        return self.put(self.get_upload_file_url(), file=filename)

    def sendUploadProgress(self, sent, total):
        log("Download %d from %s" % (sent, total,))
        self.uploadProgressCallback(total, sent)