from django.urls import path

from . import consumers


websocket_urlpatterns = [
    path('ws/whatsapp/listing/<int:listing_id>/', consumers.WhatsAppListingConsumer.as_asgi()),
    path('ws/whatsapp/index/', consumers.WhatsAppIndexConsumer.as_asgi()),
]
