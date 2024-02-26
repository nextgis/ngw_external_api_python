from .ngw_abstract_vector_resource import NGWAbstractVectorResource


class NGWPostgisLayer(NGWAbstractVectorResource):
    type_id = "postgis_layer"
