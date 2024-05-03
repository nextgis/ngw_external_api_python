from typing import Any, Dict, Tuple

from qgis.core import QgsProviderRegistry

from nextgis_connect.ngw_api.core.ngw_resource import NGWResource
from nextgis_connect.ngw_connection.ngw_connections_manager import (
    NgwConnectionsManager,
)


class NGWTmsConnection(NGWResource):
    type_id = "tmsclient_connection"
    type_title = "NGW TMS Connection"

    @property
    def connection_info(self) -> Dict[str, Any]:
        return self._json[self.type_id]


class NGWTmsLayer(NGWResource):
    type_id = "tmsclient_layer"
    type_title = "NGW TMS Layer"

    @property
    def service_resource_id(self) -> int:
        return self._json[self.type_id]["connection"]["id"]

    def layer_params(
        self, tms_connection: NGWTmsConnection
    ) -> Tuple[str, str, str]:
        connection_info = tms_connection.connection_info
        layer_info = self._json[self.type_id]

        params = {"type": "xyz", "url": connection_info["url_template"]}
        params["zmin"] = layer_info.get("minzoom")
        params["zmax"] = layer_info.get("maxzoom")

        connections_manager = NgwConnectionsManager()
        connection = connections_manager.connection(self.connection_id)
        assert connection is not None
        if (
            params["url"].startswith(connection.url)
            and connection.auth_config_id is not None
        ):
            params["authcfg"] = connection.auth_config_id
        elif (
            connection_info.get("username") is not None
            and connection_info.get("password") is not None
        ):
            params["username"] = connection_info.get("username")
            params["password"] = connection_info.get("password")

        params = {
            key: value for key, value in params.items() if value is not None
        }

        provider_metadata = QgsProviderRegistry.instance().providerMetadata(
            "wms"
        )
        return provider_metadata.encodeUri(params), self.display_name, "wms"
