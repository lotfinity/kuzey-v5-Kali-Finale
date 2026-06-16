import json

from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async

from .models import Listing


def whatsapp_listing_group(listing_id):
    return 'whatsapp_listing_%s' % int(listing_id)


def whatsapp_index_group():
    return 'whatsapp_index'


class WhatsAppListingConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.listing_id = int(self.scope['url_route']['kwargs']['listing_id'])
        exists = await self._listing_exists(self.listing_id)
        if not exists:
            await self.close(code=4404)
            return
        self.group_name = whatsapp_listing_group(self.listing_id)
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        await self.send_json({
            'type': 'whatsapp.connected',
            'listingId': self.listing_id,
        })

    async def disconnect(self, close_code):
        if getattr(self, 'group_name', None):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def whatsapp_message(self, event):
        await self.send_json({
            'type': 'whatsapp.message',
            'message': event.get('message'),
            'conversation': event.get('conversation'),
        })

    async def whatsapp_conversation_updated(self, event):
        await self.send_json({
            'type': 'whatsapp.conversation_updated',
            'conversation': event.get('conversation'),
        })

    async def send_json(self, payload):
        await self.send(text_data=json.dumps(payload, ensure_ascii=False))

    @database_sync_to_async
    def _listing_exists(self, listing_id):
        return Listing.objects.filter(pk=listing_id).exists()


class WhatsAppIndexConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.group_name = whatsapp_index_group()
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        await self.send_json({'type': 'whatsapp.index.connected'})

    async def disconnect(self, close_code):
        if getattr(self, 'group_name', None):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def whatsapp_conversation_updated(self, event):
        await self.send_json({
            'type': 'whatsapp.conversation_updated',
            'conversation': event.get('conversation'),
        })

    async def whatsapp_message(self, event):
        await self.send_json({
            'type': 'whatsapp.message',
            'message': event.get('message'),
            'conversation': event.get('conversation'),
        })

    async def send_json(self, payload):
        await self.send(text_data=json.dumps(payload, ensure_ascii=False))
