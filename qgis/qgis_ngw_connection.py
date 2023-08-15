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
import time
import urllib.parse

from qgis.PyQt.QtCore import (
    QBuffer, QByteArray, QEventLoop, QFile, QIODevice, QObject, QTimer, QUrl)
from qgis.PyQt.QtNetwork import QNetworkRequest

from qgis.core import QgsNetworkAccessManager

from ..core.ngw_error import NGWError

from ..utils import log

from .compat_qgis import CompatQgis
from .compat_qgis import CompatQt


UPLOAD_FILE_URL = '/api/component/file_upload/'
GET_VERSION_URL = '/api/component/pyramid/pkg_version'
TUS_UPLOAD_FILE_URL = '/api/component/file_upload/'
TUS_VERSION = '1.0.0'
TUS_CHUNK_SIZE = 16777216
CLIENT_TIMEOUT = 3 * 60 * 1000

class QgsNgwConnection(QObject):

    AbilityBaseMap = list(range(1))


    """docstring for QgsNgwConnection"""
    def __init__(self, conn_settings, parent=None):
        super().__init__(parent)

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


    def _get_json_param(self, j, key, def_val):
        try:
            return j[key]
        except:
            return def_val


    def get(self, sub_url, params=None, **kwargs):
        return self.__request_json(sub_url, 'GET', params, True, **kwargs)

    def post(self, sub_url, params=None, **kwargs):
        return self.__request_json(sub_url, 'POST', params, True, **kwargs)

    def put(self, sub_url, params=None, **kwargs):
        return self.__request_json(sub_url, 'PUT', params, True, **kwargs)

    def patch(self, sub_url, params=None, **kwargs):
        return self.__request_json(sub_url, 'PATCH', params, True, **kwargs)

    def delete(self, sub_url, params=None, **kwargs):
        return self.__request_json(sub_url, 'DELETE', params, True, **kwargs)


    def post_lunkwill(self, sub_url, params=None, extended_log=False, **kwargs):
        """
        Make a long POST request to NGW server which supports "Lunkwill".
        """
        default_wait_ms = 2000

        # Add specific header to the first request.
        headers = {'X-Lunkwill': 'suggest'}
        rep, j = self.__request_rep_json(sub_url, 'POST', params, headers, True, **kwargs)

        # Check that server supports lunkwill and return reply immideately if not (the request just has been processed
        # as usual NGW API request).
        hname = ('Content-Type').encode('utf-8')
        if rep.hasRawHeader(hname):
            hvalue = bytes(rep.rawHeader(hname)).decode()
            hreqvalue = 'application/vnd.lunkwill.request-summary+json'
            if hreqvalue in hvalue: # search for required substring, avoiding check for things like "; charset=utf-8"
                # Send "summary" requests periodically to check long request's status.
                # Make final "response" request with usual NGW json response after receiving "ready" status.
                summary_failed_attempts = 3
                summary_failed = 0
                request_id = j['id']

                if not extended_log:
                    log('Skip lunkwill summary requests logging for id "{}"'.format(request_id))

                while True:
                    status = j['status']
                    delay_ms = self._get_json_param(j, 'delay_ms', default_wait_ms) # this param could be not included into reply
                    retry_ms = self._get_json_param(j, 'retry_ms', default_wait_ms)

                    if summary_failed == 0:
                        wait_ms = delay_ms / 1000
                    elif summary_failed <= summary_failed_attempts:
                        wait_ms = retry_ms / 1000
                    else:
                        raise Exception('Lunkwill request aborted: failed summary requests count exceeds maximum')

                    if status == 'processing' or status == 'spooled' or status == 'buffering':
                        time.sleep(wait_ms)
                        try:
                            sub_url = '/api/lunkwill/{}/summary'.format(request_id)
                            j = self.__request_json(sub_url, 'GET', None, extended_log, **kwargs)
                            summary_failed = 0
                        except:
                            if extended_log:
                                log('Lunkwill summary request failed. Try again')
                            summary_failed += 1

                    elif status == 'ready':
                        sub_url = '/api/lunkwill/{}/response'.format(request_id)
                        j = self.__request_json(sub_url, 'GET', None, True, **kwargs)
                        break

                    else:
                        raise Exception('Lunkwill request failed on server. Reply: {}'.format(str(j)))

        rep.deleteLater()
        del rep

        return j


    def __request_rep(self, sub_url, method, badata=None, params=None, headers=None, do_log=True, **kwargs):
        json_data = None
        if params:
            json_data = json.dumps(params).encode('utf-8')
        if 'json' in kwargs:
            json_data = json.dumps(kwargs['json']).encode('utf-8')

        filename = kwargs.get("file")

        url = urllib.parse.urljoin(self.server_url, sub_url)

        if do_log:
            log(u"Request\nmethod: {}\nurl: {}\njson: {}\nheaders: {}\nfile: {}\nbyte data size: {}".format(
                    method,
                    url,
                    #type(json_data),
                    json_data.decode('unicode_escape') if json_data is not None else None,
                    headers,
                    filename.encode('utf-8') if filename else '-',
                    badata.size() if badata else '-'
                )
            )

        req = QNetworkRequest(QUrl(url))

        if all(map(len, self.__auth)):
            authstr = ('%s:%s' % self.__auth).encode('utf-8')
            authstr = QByteArray(authstr).toBase64()
            authstr = QByteArray(('Basic ').encode('utf-8')).append(authstr)
            req.setRawHeader(("Authorization").encode('utf-8'), authstr)

        if headers is not None: # add custom headers
            for k, v in list(headers.items()):
                hkey = k.encode('utf-8')
                hval = v.encode('utf-8')
                req.setRawHeader(hkey, hval)

        iodevice = None # default to None, not to "QBuffer(QByteArray())" - otherwise random crashes at post() in QGIS 3
        if badata is not None:
            iodevice = QBuffer(badata)
        elif filename is not None:
            iodevice = QFile(filename)
        elif json_data is not None:
            req.setHeader(QNetworkRequest.ContentTypeHeader, "application/json")
            json_data = QByteArray(json_data)
            iodevice = QBuffer(json_data)

        if iodevice is not None:
            iodevice.open(QIODevice.ReadOnly)

        loop = QEventLoop() #loop = QEventLoop(self)
        nam = QgsNetworkAccessManager.instance()

        has_redirect_policy = False
        if CompatQt.has_redirect_policy():
            nam.setRedirectPolicy(QNetworkRequest.NoLessSafeRedirectPolicy)
            has_redirect_policy = True

        if method == "GET":
            rep = nam.get(req)
        elif method == "POST":
            rep = nam.post(req, iodevice)
        elif method == "DELETE":
            rep = nam.deleteResource(req)
        else:
            rep = nam.sendCustomRequest(req, method.encode('utf-8'), iodevice)

        rep.finished.connect(loop.quit)
        if filename is not None:
            rep.uploadProgress.connect(self.sendUploadProgress)

        # In our current approach we use QEventLoop to wait QNetworkReply finished() signal. This could lead to infinite loop
        # in the case when finished() signal 1) is not fired at all or 2) fired right after isFinished() method but before loop.exec_().
        # We need some kind of guard for that OR we need to use another approach to wait for network replies (e.g. fully asynchronous
        # approach which is actually should be used when dealing with QNetworkAccessManager).
        # NOTE: actualy this is also our client timeout for any single request to NGW. We are able to set it to some not-large value because
        # we use tus uplod for large files => we do not warry that large files will not be uploaded this way.
        if not rep.isFinished(): # isFinished() checks that finished() is emmited before, but not after this method
            timer = QTimer()
            timer.setSingleShot(True)
            timer.timeout.connect(loop.quit)
            timer.start(CLIENT_TIMEOUT)

            loop.exec_()

        rep.finished.disconnect(loop.quit)

        loop.deleteLater()
        del loop

        if iodevice is not None:
            iodevice.close()

        # Indicate that request has been timed out by QGIS.
        # TODO: maybe use QgsNetworkAccessManager::requestTimedOut()?
        if rep.error() == 5:
            log('Connection error qt code: 5 (QNetworkReply::OperationCanceledError)')
            raise NGWError(NGWError.TypeRequestError, 'Connection has been aborted or closed', req.url().toString(),
                self.tr('Connection closed by QGIS. Increase timeout (Settings -> Options -> Network) to 300000 and retry.'),
                need_reconnect=False)

        if rep.error() > 0 and rep.error() < 10:
            log( "Connection error qt code: {}".format(rep.error()) )
            raise NGWError(NGWError.TypeRequestError, "Connection error qt code: {}".format(rep.error()), req.url().toString())

        return req, rep


    def __request_rep_json(self, sub_url, method, params=None, headers=None, do_log=True, **kwargs):
        req, rep = self.__request_rep(sub_url, method, badata=None, params=params, headers=headers, do_log=do_log, **kwargs)

        status_code = rep.attribute(QNetworkRequest.HttpStatusCodeAttribute)

        data = rep.readAll()
        rep_str = CompatQgis.decode_reply_escape(data)
        rep_str_log = CompatQgis.decode_reply_escape_log(rep_str)

        #if  status_code / 100 != 2:
        if status_code is not None and int(str(status_code)[:1]) != 2:
            log(u"Response\nerror status_code {}\nmsg: {}".format(status_code, rep_str_log))

            ngw_message_present = False
            try:
                json.loads(bytes(data).decode('utf-8'))
                ngw_message_present = True
            except Exception as e:
                pass

            if ngw_message_present:
                raise NGWError(NGWError.TypeNGWError, rep_str, req.url().toString())
            else:
                raise NGWError(NGWError.TypeRequestError, "Response status code is %s" % status_code, req.url().toString())

        try:
            json_response = json.loads(bytes(data).decode('utf-8'))
        except:
            log(u"Response\nerror response JSON parse\n%s" % rep_str_log)
            raise NGWError(NGWError.TypeNGWUnexpectedAnswer, "", req.url().toString())

        return rep, json_response


    def __request_json(self, sub_url, method, params=None, do_log=True, **kwargs):
        rep, j = self.__request_rep_json(sub_url, method, params=params, headers=None, do_log=do_log, **kwargs)

        rep.deleteLater()
        del rep

        return j


    def get_upload_file_url(self):
        return UPLOAD_FILE_URL

    def upload_file(self, filename, callback):
        self.uploadProgressCallback = callback
        return self.put(self.get_upload_file_url(), file=filename)


    def tus_upload_file(self, filename, callback, extended_log=False):
        """
        Implements tus protocol to upload a file to NGW.
        Note: This method internally uses self methods to send synchronous HTTP requests (which internally use
        QgsNetworkAccessManager) so we cannot put it to some separate class or module.
        """
        callback(0, 0, 0) # show in the progress bar that 0% is loaded currently
        self.uploadProgressCallback = callback

        file = QFile(filename)
        if not file.open(QIODevice.ReadOnly):
            raise Exception('Failed to open file for tus uplod')
        file_size = file.size()

        # Initiate upload process by sending specific "create" request with a void body.
        create_hdrs = {
            'Tus-Resumable': TUS_VERSION,
            'Content-Length': '0',
            #'Upload-Defer-Length': ,
            'Upload-Length': str(file_size),
            #'Upload-Metadata': 'name {}'.format(base64name)
        }
        create_req, create_rep = self.__request_rep(TUS_UPLOAD_FILE_URL, 'POST', None, None, create_hdrs, True)
        create_rep_code = create_rep.attribute(QNetworkRequest.HttpStatusCodeAttribute)
        if create_rep_code == 413:
            raise NGWError(NGWError.TypeRequestError, 'HTTP 413: Payload is too large', TUS_UPLOAD_FILE_URL,
                self.tr('File is too large for uploading'), need_reconnect=False)
        if create_rep_code != 201:
            raise Exception('Failed to start tus uploading')
        location_hdr = ('Location').encode('utf-8')
        location = bytes(create_rep.rawHeader(location_hdr)).decode()
        create_rep.deleteLater()
        del create_rep

        file_guid = location.split('/')[-1]
        file_upload_url = TUS_UPLOAD_FILE_URL + file_guid
        max_retry_count = 3
        bytes_sent = 0

        # Allow to skip logging of PATCH requests. Helpful when a large file is being uploaded.
        # Note: QGIS 3 has a hardcoded limit of log messages.
        if not extended_log:
            log('Skip PATCH requests logging during uploading of file "{}"'.format(file_guid))

        # Upload file chunk-by-chunk.
        while True:
            badata = QByteArray(file.read(TUS_CHUNK_SIZE))
            if badata.isEmpty(): # end of data OR some error
                break
            bytes_read = badata.size()

            if extended_log:
                log("Upload %d from %s" % (bytes_sent, file_size,))
            self.sendUploadProgress(bytes_sent, file_size)

            chunk_hdrs = {
                'Tus-Resumable': TUS_VERSION,
                'Content-Type': 'application/offset+octet-stream',
                'Content-Length': str(bytes_read),
                'Upload-Offset': str(bytes_sent)
            }
            retries = 0
            while retries < max_retry_count:
                chunk_req, chunk_rep = self.__request_rep(file_upload_url, 'PATCH', badata, None, chunk_hdrs, extended_log)
                chunk_rep_code = chunk_rep.attribute(QNetworkRequest.HttpStatusCodeAttribute)
                chunk_rep.deleteLater()
                del chunk_rep
                if chunk_rep_code == 204:
                    break
                retries += 1
                log('Retry chunk upload')

            if retries == max_retry_count:
                break

            bytes_sent += bytes_read
            if extended_log:
                log('Tus-uploaded chunk of {} bytes. Now {} of overall {} bytes are uploaded'.format(bytes_read, bytes_sent, file_size))

        file.close()

        if bytes_sent < file_size:
            raise Exception('Failed to upload file via tus')

        callback(1, 1, 100) # show in the progress bar that 100% is loaded

        # Finally GET and return NGW result of uploaded file.
        return self.get(file_upload_url)


    def sendUploadProgress(self, sent, total):
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
