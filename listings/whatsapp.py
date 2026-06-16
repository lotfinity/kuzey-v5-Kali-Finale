import json
import logging
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from .models import Listing, WhatsAppConversation, WhatsAppIdentityAlias, WhatsAppMessage
from .consumers import whatsapp_index_group, whatsapp_listing_group

logger = logging.getLogger(__name__)


def _digits(value):
    return re.sub(r'\D+', '', str(value or ''))


def _string_value(value):
    if isinstance(value, dict):
        return str(value.get('_serialized') or value.get('id') or value.get('user') or '').strip()
    return str(value or '').strip()


def normalize_phone(value):
    digits = _digits(value)
    if digits.startswith('00'):
        digits = digits[2:]
    default_code = _digits(getattr(settings, 'WAHA_DEFAULT_COUNTRY_CODE', '90'))
    if digits.startswith('0') and default_code:
        digits = default_code + digits.lstrip('0')
    elif len(digits) == 10 and default_code:
        digits = default_code + digits
    return digits


def chat_id_for_phone(value):
    digits = normalize_phone(value)
    return '%s@c.us' % digits if digits else ''


def chat_id_aliases(value):
    raw = str(value or '').strip()
    aliases = set()
    if raw:
        aliases.add(raw)
        if raw.endswith('@lid'):
            return aliases
        digits = normalize_phone(raw)
        if digits:
            aliases.add('%s@c.us' % digits)
            aliases.add('%s@s.whatsapp.net' % digits)
    return aliases


def _alias_values(value):
    aliases = chat_id_aliases(value)
    raw = _string_value(value)
    if raw:
        aliases.add(raw)
    return {alias for alias in aliases if alias}


def _session():
    return getattr(settings, 'WAHA_SESSION_DEFAULT', 'default') or 'default'


def _waha_configured():
    return bool(getattr(settings, 'WAHA_URL', '') and getattr(settings, 'WAHA_API_KEY', ''))


def _waha_request(method, path, body=None, query=None):
    if not _waha_configured():
        raise RuntimeError('WAHA_URL and WAHA_API_KEY are not configured')

    base_url = getattr(settings, 'WAHA_URL', '').rstrip('/')
    url = '%s%s' % (base_url, path)
    if query:
        filtered = {key: value for key, value in query.items() if value is not None}
        if filtered:
            url = '%s?%s' % (url, urllib.parse.urlencode(filtered))

    data = None
    headers = {
        'Accept': 'application/json, text/plain;q=0.9, */*;q=0.8',
        'X-Api-Key': getattr(settings, 'WAHA_API_KEY', ''),
        'User-Agent': 'kuzey-whatsapp-widget/1.0',
    }
    if body is not None:
        data = json.dumps(body).encode('utf-8')
        headers['Content-Type'] = 'application/json'

    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=12) as response:
            payload = response.read().decode('utf-8')
            content_type = response.headers.get('content-type', '')
            if 'application/json' in content_type and payload:
                return json.loads(payload)
            return payload
    except urllib.error.HTTPError as exc:
        try:
            payload = exc.read().decode('utf-8')
            parsed = json.loads(payload)
            message = parsed.get('message') or parsed.get('error') or payload
        except Exception:
            message = exc.reason
        raise RuntimeError('WAHA API error %s: %s' % (exc.code, message))
    except urllib.error.URLError as exc:
        raise RuntimeError('WAHA API request failed: %s' % exc.reason)


def _store_identity_alias(conversation, alias, canonical_id='', phone_number='', source=''):
    alias = _string_value(alias)
    if not alias:
        return None
    phone_number = normalize_phone(phone_number or canonical_id or alias)
    defaults = {
        'conversation': conversation,
        'canonical_id': _string_value(canonical_id) or conversation.chat_id,
        'phone_number': phone_number or conversation.phone_number,
        'source': source,
    }
    identity, created = WhatsAppIdentityAlias.objects.get_or_create(
        session=conversation.session or _session(),
        alias=alias,
        defaults=defaults,
    )
    if not created:
        changed = False
        for key, value in defaults.items():
            if getattr(identity, key) != value:
                setattr(identity, key, value)
                changed = True
        if changed:
            identity.save()
    return identity


def _seed_conversation_aliases(conversation, source='listing'):
    for alias in _alias_values(conversation.chat_id) | _alias_values(conversation.phone_number):
        _store_identity_alias(
            conversation,
            alias,
            canonical_id=conversation.chat_id,
            phone_number=conversation.phone_number,
            source=source,
        )


def _lid_mapping_from_waha(session, chat_id):
    if not _waha_configured() or '@lid' not in chat_id:
        return None
    try:
        mapping = _waha_request(
            'GET',
            '/api/%s/lids/%s' % (
                urllib.parse.quote(session or _session(), safe=''),
                urllib.parse.quote(chat_id, safe=''),
            ),
        )
    except Exception as exc:
        logger.warning('WAHA LID lookup failed session=%s lid=%s error=%s', session, chat_id, exc)
        return None
    if not isinstance(mapping, dict):
        return None
    lid = _string_value(mapping.get('lid'))
    pn = _string_value(mapping.get('pn') or mapping.get('phone') or mapping.get('phoneNumber'))
    if not lid or not pn:
        return None
    return {'lid': lid, 'pn': pn}


def _conversation_for_identity(chat_id, session):
    aliases = _alias_values(chat_id)
    conversation = WhatsAppConversation.objects.filter(
        identity_aliases__session=session,
        identity_aliases__alias__in=aliases,
    ).first()
    if conversation:
        return conversation

    conversation = WhatsAppConversation.objects.filter(chat_id__in=aliases, session=session).first()
    if conversation:
        _seed_conversation_aliases(conversation, source='direct_match')
        return conversation

    mapping = _lid_mapping_from_waha(session, chat_id)
    if not mapping:
        return None

    mapped_aliases = _alias_values(mapping['pn']) | _alias_values(mapping['lid'])
    conversation = WhatsAppConversation.objects.filter(chat_id__in=mapped_aliases, session=session).first()
    if not conversation:
        phone = normalize_phone(mapping['pn'])
        conversation = WhatsAppConversation.objects.filter(phone_number=phone, session=session).first()
    if conversation:
        for alias in mapped_aliases:
            _store_identity_alias(
                conversation,
                alias,
                canonical_id=mapping['pn'],
                phone_number=mapping['pn'],
                source='waha_lid',
            )
    return conversation


def _resolve_conversation(listing):
    phone = getattr(listing, 'phone', '')
    phone_number = normalize_phone(phone)
    chat_id = chat_id_for_phone(phone)
    if not chat_id:
        return None
    display_name = getattr(listing, 'from_whom', '') or ''
    if not display_name:
        display_name = 'Listing owner'
    conversation, _ = WhatsAppConversation.objects.get_or_create(
        listing=listing,
        chat_id=chat_id,
        session=_session(),
        defaults={
            'phone_number': phone_number,
            'display_name': display_name,
        },
    )
    changed = False
    if conversation.phone_number != phone_number:
        conversation.phone_number = phone_number
        changed = True
    if display_name and conversation.display_name != display_name:
        conversation.display_name = display_name
        changed = True
    if changed:
        conversation.save(update_fields=['phone_number', 'display_name', 'updated_at'])
    _seed_conversation_aliases(conversation)
    return conversation


def _message_id(record):
    value = record.get('id') if isinstance(record, dict) else None
    return _string_value(value or record.get('_serialized'))


def _message_body(record):
    nested = record.get('_data') if isinstance(record.get('_data'), dict) else {}
    candidates = [
        record.get('body'),
        record.get('text'),
        record.get('caption'),
        nested.get('body'),
        nested.get('caption'),
    ]
    for candidate in candidates:
        text = str(candidate or '').strip()
        if text:
            return text
    return ''


def _message_sent_at(record):
    nested = record.get('_data') if isinstance(record.get('_data'), dict) else {}
    value = record.get('timestamp') or record.get('t') or nested.get('t')
    try:
        value = int(value)
    except (TypeError, ValueError):
        return timezone.now()
    if value > 100000000000:
        value = value / 1000.0
    return datetime.fromtimestamp(value, tz=timezone.utc)


def _waha_webhook_record(data):
    payload = data.get('payload') if isinstance(data.get('payload'), dict) else data
    if isinstance(payload.get('message'), dict):
        record = payload.get('message').copy()
        for key in ('chatId', 'from', 'to', 'fromMe', 'session'):
            if key not in record and key in payload:
                record[key] = payload.get(key)
        return record
    return payload


def _record_chat_id(record):
    nested = record.get('_data') if isinstance(record.get('_data'), dict) else {}
    info = nested.get('Info') if isinstance(nested.get('Info'), dict) else {}
    chat_id = _string_value(record.get('chatId') or nested.get('chatId') or nested.get('Chat') or info.get('Chat'))
    sender = _string_value(record.get('from') or nested.get('from') or info.get('Sender'))
    receiver = _string_value(record.get('to') or nested.get('to'))
    from_me = record.get('fromMe') is True or nested.get('fromMe') is True
    if from_me:
        return receiver or chat_id or sender
    return chat_id or sender or receiver


def _store_message(conversation, record, default_direction=None):
    if not isinstance(record, dict):
        return None
    nested = record.get('_data') if isinstance(record.get('_data'), dict) else {}
    from_me = record.get('fromMe') is True or nested.get('fromMe') is True
    direction = default_direction or (WhatsAppMessage.DIRECTION_OUT if from_me else WhatsAppMessage.DIRECTION_IN)
    message_id = _message_id(record)
    defaults = {
        'direction': direction,
        'sender': _string_value(record.get('from') or nested.get('from')),
        'body': _message_body(record),
        'message_type': str(record.get('type') or nested.get('type') or 'text')[:40],
        'sent_at': _message_sent_at(record),
        'raw_payload': json.dumps(record, ensure_ascii=False, default=str),
    }
    if message_id:
        message, created = WhatsAppMessage.objects.get_or_create(
            conversation=conversation,
            waha_message_id=message_id,
            defaults=defaults,
        )
        if not created:
            changed = False
            for key, value in defaults.items():
                if getattr(message, key) != value:
                    setattr(message, key, value)
                    changed = True
            if changed:
                message.save()
        return message
    return WhatsAppMessage.objects.create(conversation=conversation, waha_message_id='', **defaults)


def _serialize_message(message):
    sent_at = message.sent_at or message.created_at
    return {
        'id': message.id,
        'wahaMessageId': message.waha_message_id,
        'direction': message.direction,
        'sender': message.sender,
        'body': message.body,
        'type': message.message_type,
        'sentAt': sent_at.isoformat() if sent_at else '',
    }


def _serialize_conversation(conversation):
    latest_message = getattr(conversation, '_latest_message', None)
    unread_count = getattr(conversation, '_unread_count', 0)
    listing = getattr(conversation, 'listing', None)
    image_url = ''
    if listing is not None:
        try:
            first_image = listing.images.order_by('order', 'id').first()
            if first_image and getattr(first_image, 'image', None):
                image_url = first_image.image.url
        except Exception:
            image_url = ''
    return {
        'id': conversation.id,
        'listingId': conversation.listing_id,
        'listingTitle': getattr(listing, 'title', '') if listing is not None else '',
        'listingPrice': getattr(listing, 'price', None) if listing is not None else None,
        'listingUrl': '/listing/%s/' % conversation.listing_id if conversation.listing_id else '',
        'listingImage': image_url,
        'chatId': conversation.chat_id,
        'phoneNumber': conversation.phone_number,
        'displayName': conversation.display_name,
        'session': conversation.session,
        'lastSyncedAt': conversation.last_synced_at.isoformat() if conversation.last_synced_at else '',
        'updatedAt': conversation.updated_at.isoformat() if conversation.updated_at else '',
        'unreadCount': unread_count,
        'latestMessage': _serialize_message(latest_message) if latest_message else None,
    }


def _conversation_unread_count(conversation):
    latest_out = conversation.messages.filter(
        direction=WhatsAppMessage.DIRECTION_OUT,
    ).order_by('-sent_at', '-id').first()
    incoming = conversation.messages.filter(direction=WhatsAppMessage.DIRECTION_IN)
    if latest_out:
        if latest_out.sent_at:
            incoming = incoming.filter(sent_at__gt=latest_out.sent_at)
        else:
            incoming = incoming.filter(id__gt=latest_out.id)
    return incoming.count()


def _decorate_conversation(conversation):
    conversation._latest_message = conversation.messages.order_by('-sent_at', '-id').first()
    conversation._unread_count = _conversation_unread_count(conversation)
    return conversation


def broadcast_whatsapp_message(message):
    if message is None:
        return
    conversation = _decorate_conversation(message.conversation)
    payload = {
        'type': 'whatsapp.message',
        'message': _serialize_message(message),
        'conversation': _serialize_conversation(conversation),
    }
    channel_layer = get_channel_layer()
    if channel_layer is None:
        logger.warning('WhatsApp message %s not broadcast: no channel layer', message.id)
        return
    async_to_sync(channel_layer.group_send)(
        whatsapp_listing_group(conversation.listing_id),
        payload,
    )
    async_to_sync(channel_layer.group_send)(
        whatsapp_index_group(),
        payload,
    )
    logger.info(
        'WhatsApp message %s broadcast to listing %s',
        message.id,
        conversation.listing_id,
    )


def sync_conversation_from_waha(conversation, limit=50):
    session = urllib.parse.quote(conversation.session or _session(), safe='')
    chat_id = urllib.parse.quote(conversation.chat_id, safe='')
    messages = _waha_request(
        'GET',
        '/api/%s/chats/%s/messages' % (session, chat_id),
        query={'limit': limit, 'offset': 0},
    )
    if isinstance(messages, dict):
        values = messages.get('messages') or messages.get('data') or []
    else:
        values = messages
    if isinstance(values, list):
        for record in values:
            _store_message(conversation, record)
    conversation.last_synced_at = timezone.now()
    conversation.save(update_fields=['last_synced_at', 'updated_at'])


@require_GET
def listing_conversation(request, listing_id):
    listing = get_object_or_404(Listing.objects.select_related('realtor'), pk=listing_id)
    conversation = _resolve_conversation(listing)
    if conversation is None:
        return JsonResponse({
            'ok': False,
            'error': 'No WhatsApp phone number is attached to this listing.',
            'messages': [],
        }, status=404)

    sync_error = ''
    should_sync = request.GET.get('sync', '1') != '0'
    if should_sync and _waha_configured():
        try:
            sync_conversation_from_waha(conversation, limit=int(request.GET.get('limit', 50)))
        except Exception as exc:
            sync_error = str(exc)

    messages = conversation.messages.all().order_by('sent_at', 'id')
    limit = max(1, min(int(request.GET.get('limit', 50)), 200))
    messages = messages[max(messages.count() - limit, 0):]
    return JsonResponse({
        'ok': True,
        'listingId': listing.id,
        'chatId': conversation.chat_id,
        'phoneNumber': conversation.phone_number,
        'displayName': conversation.display_name,
        'session': conversation.session,
        'wahaConfigured': _waha_configured(),
        'syncError': sync_error,
        'messages': [_serialize_message(message) for message in messages],
    })


@require_GET
def conversations_index(request):
    limit = max(1, min(int(request.GET.get('limit', 50)), 200))
    conversations = list(
        WhatsAppConversation.objects.select_related('listing').prefetch_related('messages')[:limit]
    )
    conversations = [_decorate_conversation(conversation) for conversation in conversations]
    total_unread = sum(conversation._unread_count for conversation in conversations)
    return JsonResponse({
        'ok': True,
        'wahaConfigured': _waha_configured(),
        'totalUnread': total_unread,
        'conversations': [_serialize_conversation(conversation) for conversation in conversations],
    })


@require_GET
def conversation_messages(request, conversation_id):
    conversation = get_object_or_404(
        WhatsAppConversation.objects.select_related('listing'),
        pk=conversation_id,
    )
    should_sync = request.GET.get('sync', '0') != '0'
    sync_error = ''
    if should_sync and _waha_configured():
        try:
            sync_conversation_from_waha(conversation, limit=int(request.GET.get('limit', 50)))
        except Exception as exc:
            sync_error = str(exc)
    messages = conversation.messages.all().order_by('sent_at', 'id')
    limit = max(1, min(int(request.GET.get('limit', 80)), 200))
    messages = messages[max(messages.count() - limit, 0):]
    conversation = _decorate_conversation(conversation)
    return JsonResponse({
        'ok': True,
        'conversation': _serialize_conversation(conversation),
        'wahaConfigured': _waha_configured(),
        'syncError': sync_error,
        'messages': [_serialize_message(message) for message in messages],
    })


@require_POST
def send_conversation_message(request, conversation_id):
    conversation = get_object_or_404(
        WhatsAppConversation.objects.select_related('listing'),
        pk=conversation_id,
    )
    if not _waha_configured():
        return JsonResponse({'ok': False, 'error': 'WAHA_URL and WAHA_API_KEY are not configured.'}, status=503)
    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
    except ValueError:
        payload = request.POST
    text = str(payload.get('message') or payload.get('text') or '').strip()
    if not text:
        return JsonResponse({'ok': False, 'error': 'Message text is required.'}, status=400)
    try:
        result = _waha_request('POST', '/api/sendText', {
            'session': conversation.session or _session(),
            'chatId': conversation.chat_id,
            'text': text,
        })
    except Exception as exc:
        return JsonResponse({'ok': False, 'error': str(exc)}, status=502)
    record = result if isinstance(result, dict) else {
        'body': text,
        'fromMe': True,
        'type': 'text',
        'timestamp': int(timezone.now().timestamp()),
    }
    message = _store_message(conversation, record, default_direction=WhatsAppMessage.DIRECTION_OUT)
    broadcast_whatsapp_message(message)
    return JsonResponse({'ok': True, 'message': _serialize_message(message), 'raw': result})


@require_POST
def send_listing_message(request, listing_id):
    listing = get_object_or_404(Listing.objects.select_related('realtor'), pk=listing_id)
    conversation = _resolve_conversation(listing)
    if conversation is None:
        return JsonResponse({'ok': False, 'error': 'No WhatsApp phone number is attached to this listing.'}, status=404)
    if not _waha_configured():
        return JsonResponse({'ok': False, 'error': 'WAHA_URL and WAHA_API_KEY are not configured.'}, status=503)

    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
    except ValueError:
        payload = request.POST
    text = str(payload.get('message') or payload.get('text') or '').strip()
    if not text:
        return JsonResponse({'ok': False, 'error': 'Message text is required.'}, status=400)

    try:
        result = _waha_request('POST', '/api/sendText', {
            'session': conversation.session or _session(),
            'chatId': conversation.chat_id,
            'text': text,
        })
    except Exception as exc:
        return JsonResponse({'ok': False, 'error': str(exc)}, status=502)
    record = result if isinstance(result, dict) else {
        'body': text,
        'fromMe': True,
        'type': 'text',
        'timestamp': int(timezone.now().timestamp()),
    }
    message = _store_message(conversation, record, default_direction=WhatsAppMessage.DIRECTION_OUT)
    broadcast_whatsapp_message(message)
    return JsonResponse({'ok': True, 'message': _serialize_message(message), 'raw': result})


@csrf_exempt
@require_POST
def waha_webhook(request):
    try:
        data = json.loads(request.body.decode('utf-8') or '{}')
    except ValueError:
        data = {}
    event = data.get('event') or data.get('type') or ''
    if event == 'message.any':
        logger.info('WAHA webhook event=%s ignored: message event handles storage', event)
        return JsonResponse({'ok': True, 'stored': False, 'ignored': True, 'event': event})
    record = _waha_webhook_record(data)
    chat_id = _record_chat_id(record)
    session = str(data.get('session') or record.get('session') or _session()).strip()

    if not chat_id:
        logger.info('WAHA webhook event=%s session=%s ignored: missing chat id', event, session)
        return JsonResponse({'ok': True, 'stored': False, 'event': event})

    conversation = _conversation_for_identity(chat_id, session)
    stored = 0
    matched = 1 if conversation else 0
    if conversation:
        message = _store_message(conversation, record)
        if message:
            stored += 1
            broadcast_whatsapp_message(message)
    logger.info(
        'WAHA webhook event=%s session=%s chat=%s matched=%s stored=%s',
        event,
        session,
        chat_id,
        matched,
        stored,
    )
    return JsonResponse({'ok': True, 'stored': stored, 'event': event})
