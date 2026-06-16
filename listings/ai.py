import json
import logging
import os
import urllib.error
import urllib.request

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_POST

from .models import Listing
from .whatsapp import _resolve_conversation

logger = logging.getLogger(__name__)


def _ai_error(message, status=400):
    return JsonResponse({'ok': False, 'error': message}, status=status)


def _ai_settings():
    model = getattr(settings, 'WHATSAPP_AI_MODEL', '').strip()
    api_key = getattr(settings, 'WHATSAPP_AI_API_KEY', '').strip()
    api_base = getattr(settings, 'WHATSAPP_AI_API_BASE', '').strip()
    if not api_base and model and not model.startswith(('nvidia_nim/', 'openai/', 'anthropic/', 'gemini/')):
        api_base = 'https://aigw.whatsynaptic.com'
    if api_key and model.startswith('nvidia_nim/'):
        os.environ.setdefault('NVIDIA_NIM_API_KEY', api_key)
    if api_base and model.startswith('nvidia_nim/'):
        os.environ.setdefault('NVIDIA_NIM_API_BASE', api_base)
    return model, api_key, api_base


def _listing_context(listing):
    bits = [
        'Title: %s' % listing.title,
        'Location: %s, %s, %s' % (listing.address, listing.city, listing.state),
        'Price: %s TRY' % listing.price,
        'Deal type: %s' % listing.get_deal_type_display(),
        'Property type: %s' % (listing.property_type or 'property'),
        'Rooms: %s' % (listing.rooms_text or listing.bedrooms or ''),
        'Bathrooms: %s' % listing.bathrooms,
        'Size: %s m2 net, %s m2 gross' % (listing.m2_net or listing.sqft or '', listing.m2_gross or ''),
    ]
    optional = [
        ('Floor', listing.floor_number),
        ('Building age', listing.building_age),
        ('Heating', listing.heating),
        ('Furnished', 'yes' if listing.furnished is True else 'no' if listing.furnished is False else ''),
        ('Deposit', listing.deposit),
        ('Maintenance fee', listing.maintenance_fee),
    ]
    for label, value in optional:
        if value not in (None, ''):
            bits.append('%s: %s' % (label, value))
    if listing.description:
        bits.append('Description: %s' % listing.description[:1200])
    return '\n'.join(bits)


def _conversation_context(conversation, limit=16):
    qs = conversation.messages.order_by('-sent_at', '-id')[:limit]
    messages = list(reversed(qs))
    lines = []
    for message in messages:
        speaker = 'Me, the property hunter' if message.direction == 'out' else 'Listing contact'
        body = (message.body or '').strip()
        if body:
            lines.append('%s: %s' % (speaker, body[:800]))
    return '\n'.join(lines)


def _has_conversation_text(conversation):
    return conversation.messages.exclude(body='').exists()


def _extract_text(response):
    try:
        choice = response.choices[0]
        message = getattr(choice, 'message', None)
        if message is not None:
            content = getattr(message, 'content', None)
            if content:
                return str(content).strip()
        if isinstance(choice, dict):
            return str(choice.get('message', {}).get('content') or choice.get('text') or '').strip()
    except Exception:
        pass
    return ''


def _completion_via_openai_compatible_proxy(model, api_key, api_base, messages, temperature, max_tokens, timeout):
    base = api_base.rstrip('/')
    if not base.endswith('/v1'):
        base = base + '/v1'
    payload = json.dumps({
        'model': model,
        'messages': messages,
        'temperature': temperature,
        'max_tokens': max_tokens,
    }).encode('utf-8')
    request = urllib.request.Request(
        base + '/chat/completions',
        data=payload,
        headers={
            'Authorization': 'Bearer %s' % api_key,
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'User-Agent': 'kuzey-whatsapp-ai/1.0',
        },
        method='POST',
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode('utf-8'))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode('utf-8')[:500]
        raise RuntimeError('AI gateway error %s: %s' % (exc.code, body))


def _extract_proxy_text(response):
    try:
        return str(response['choices'][0]['message']['content']).strip()
    except Exception:
        return ''


@require_POST
def suggest_listing_reply(request, listing_id):
    if not getattr(settings, 'WHATSAPP_AI_ENABLED', True):
        return _ai_error('WhatsApp AI suggestions are disabled.', status=503)

    listing = get_object_or_404(Listing.objects.select_related('realtor'), pk=listing_id)
    conversation = _resolve_conversation(listing)
    if conversation is None:
        return _ai_error('No WhatsApp conversation is available for this listing.', status=404)

    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
    except ValueError:
        payload = {}
    draft = str(payload.get('draft') or '').strip()

    model, api_key, api_base = _ai_settings()
    mode = 'proxy' if api_base else 'litellm'
    if not model:
        return _ai_error('WHATSAPP_AI_MODEL is not configured.', status=503)
    if not api_key:
        return _ai_error('WHATSAPP_AI_API_KEY, NVIDIA_NIM_API_KEY, NVIDIA_API_KEY, or LITELLM_API_KEY is required for AI suggestions.', status=503)

    if not draft and not _has_conversation_text(conversation):
        return JsonResponse({
            'ok': True,
            'suggestion': 'Merhaba, bu ilan hâlâ müsait mi? Daireyi yatırım amaçlı değerlendiriyorum; güncel fiyat ve müsait ziyaret saatleri hakkında bilgi alabilir miyim?',
            'model': 'fallback',
            'mode': 'local',
        })

    system = (
        'You draft WhatsApp messages for the buyer-side user during a real estate hunt. '
        'The user is NOT the listing owner, NOT Kuzey Emlak, and NOT an estate agent replying to a customer. '
        'The recipient is the listing owner, realtor, or seller contact. '
        'Write from the first-person perspective of the property hunter asking about the listing. '
        'Never say "our listing", "our agency", "how can we help you", or imply that you represent Kuzey Emlak. '
        'Use the same language as the current draft or recent conversation when possible. '
        'Be warm, concise, practical, and natural. Keep it to one or two short WhatsApp sentences. '
        'Focus on availability, current price, viewing time, fees, title deed/document status, tenant status, or negotiation when relevant. '
        'Do not invent facts that are not in the listing context. '
        'Never discuss unrelated topics. '
        'If information is missing, ask one clear follow-up question. '
        'Return only the message text, with no quotes or explanation.'
    )
    user = (
        'Listing context:\n%s\n\nRecent WhatsApp conversation:\n%s\n\nCurrent buyer-side draft, if any:\n%s\n\nSuggested WhatsApp message from the property hunter to the listing contact:'
        % (_listing_context(listing), _conversation_context(conversation), draft or '(none)')
    )

    try:
        messages = [
            {'role': 'system', 'content': system},
            {'role': 'user', 'content': user},
        ]
        temperature = getattr(settings, 'WHATSAPP_AI_TEMPERATURE', 0.35)
        max_tokens = getattr(settings, 'WHATSAPP_AI_MAX_TOKENS', 120)
        timeout = getattr(settings, 'WHATSAPP_AI_TIMEOUT', 45)
        if getattr(settings, 'WHATSAPP_AI_LOG_PROMPTS', settings.DEBUG):
            logger.info(
                'WhatsApp AI suggestion prompt listing=%s mode=%s model=%s system=%r user=%r',
                listing.id,
                mode,
                model,
                system,
                user,
            )
        if api_base:
            response = _completion_via_openai_compatible_proxy(
                model,
                api_key,
                api_base,
                messages,
                temperature,
                max_tokens,
                timeout,
            )
            suggestion = _extract_proxy_text(response)
        else:
            from litellm import completion

            response = completion(
                model=model,
                api_key=api_key,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=timeout,
            )
            suggestion = _extract_text(response)
    except Exception as exc:
        return _ai_error('AI suggestion failed in %s mode: %s' % (mode, exc), status=502)

    if not suggestion:
        return _ai_error('AI suggestion returned an empty response.', status=502)

    if getattr(settings, 'WHATSAPP_AI_LOG_PROMPTS', settings.DEBUG):
        logger.info(
            'WhatsApp AI suggestion result listing=%s mode=%s model=%s suggestion=%r',
            listing.id,
            mode,
            model,
            suggestion,
        )

    return JsonResponse({
        'ok': True,
        'suggestion': suggestion,
        'model': model,
        'mode': mode,
    })
