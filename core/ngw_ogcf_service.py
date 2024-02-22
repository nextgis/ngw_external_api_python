from typing import Tuple, Optional

from qgis.core import QgsDataSourceUri

from .ngw_resource import NGWResource, DICT_TO_OBJ, LIST_DICT_TO_LIST_OBJ


class NGWOgcfService(NGWResource):
    type_id = 'ogcfserver_service'

    def _construct(self):
        super()._construct()
        # wfsserver_service
        self.ogcf = DICT_TO_OBJ(self._json[self.type_id])
        if hasattr(self.ogcf, "collections"):
            self.ogcf.layers = LIST_DICT_TO_LIST_OBJ(self.ogcf.collections)

    def get_ogcf_url(self, layer_keyname: str) -> str:
        layer = next(filter(
            lambda layer: layer.keyname == layer_keyname, self.ogcf.layers
        ))

        uri = QgsDataSourceUri()
        creds = self.get_creds_for_url()
        if creds[0] and creds[1]:
            uri.setUsername(creds[0])
            uri.setPassword(creds[1])
        uri.setParam('typename', layer_keyname)
        uri.setParam('srsname', 'OGC:CRS84')
        uri.setParam('preferCoordinatesForWfsT11', 'false')
        uri.setParam('pagingEnabled', 'false')
        uri.setParam('maxNumFeatures', str(layer.maxfeatures))
        uri.setParam('restrictToRequestBBOX', '1')
        uri.setParam('url', self.get_absolute_api_url() + '/ogcf')

        return uri.uri(True)

    def get_creds_for_url(self) -> Tuple[Optional[str], Optional[str]]:
        creds = self.get_creds()
        if not creds[0] or not creds[1]:
            return creds
        login = creds[0]
        password = creds[1].replace('&', '%26')
        return login, password

    def get_layers(self):
        return self.ogcf.layers
