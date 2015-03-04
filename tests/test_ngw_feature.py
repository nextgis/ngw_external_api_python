import os, sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


from core.ngw_connection_settings import NGWConnectionSettings
from core.ngw_connection import NGWConnection
from core.ngw_resource_factory import NGWResourceFactory

from core.ngw_resource import NGWResource
from core.ngw_vector_layer import NGWVectorLayer

from core.ngw_feature import NGWFeature

if __name__=="__main__":    
    ngw_resources_id = 1881
    ngw_feature_id = 159
    
    ngwConnectionSettings = NGWConnectionSettings("ngw", "http://demo.nextgis.ru/ngw", "administrator", "admin")
    ngwConnection = NGWConnection(ngwConnectionSettings)    
    ngwResourceFactory = NGWResourceFactory(ngwConnectionSettings)
    
    ngwResource = NGWVectorLayer(ngwResourceFactory, NGWResource.receive_resource_obj(ngwConnection, ngw_resources_id))
    ngwFeature = NGWFeature(ngw_feature_id, ngwResource)
    
    attachment_info = ngwConnection.upload_attachment(
          os.path.join(os.path.dirname(__file__), 'media', 'plaza-1.jpg')
    )
    ngwFeature.link_attachment(attachment_info)
    
    attachments = ngwFeature.get_attachments_ids()
    for attachment in attachments:
        if attachment[u'is_image'] == True:
            print ngwFeature.get_image_full_url( attachment[u'id'] )
            ngwFeature.unlink_attachment( attachment[u'id'] )