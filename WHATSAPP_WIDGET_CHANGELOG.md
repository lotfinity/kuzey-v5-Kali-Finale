# WhatsApp Widget Changelog

## Goal

Build a listing-scoped WhatsApp conversation system where Django stores all WAHA messages, listing pages render history from the database, webhook events update open widgets instantly, and later AI/translation/reply suggestions can enrich the stored conversation state.

## Current Architecture

- WAHA sends webhook events to Django.
- Django normalizes WAHA payloads and stores messages in `WhatsAppConversation` and `WhatsAppMessage`.
- Listing pages load conversation history from Django JSON endpoints.
- Django Channels pushes newly stored messages to listing widgets over WebSocket.
- Listing widgets keep their WebSocket connected while closed so the floating button can show unread arrivals.
- The widget keeps a slow HTTP fallback refresh for resilience.

## Completed

- Downloaded and inspected the WAHA wrapper package.
- Added `.env` loading for local WAHA settings.
- Added WAHA configuration:
  - `WAHA_URL`
  - `WAHA_API_KEY`
  - `WAHA_SESSION_DEFAULT`
  - `WAHA_DEFAULT_COUNTRY_CODE`
- Added database models:
  - `WhatsAppConversation`
  - `WhatsAppMessage`
- Added migration:
  - `listings/migrations/0014_whatsappconversation_whatsappmessage.py`
- Added Django WhatsApp API:
  - `GET /api/whatsapp/listing/<listing_id>/conversation`
  - `POST /api/whatsapp/listing/<listing_id>/send`
  - `POST /api/whatsapp/webhook`
- Added admin views for conversations and messages.
- Rebuilt the widget as a real conversation renderer.
- Adapted the widget UI to match the provided pure CSS/JS WhatsApp zip:
  - WhatsApp green top/status bar
  - WhatsApp user bar
  - wallpaper chat background
  - exact sent/received bubble colors and tails
  - Roboto message font
  - fixed 50px composer
  - white text input
  - green circular send button
- Created end-to-end test listing:
  - `/en/listing/135/`
  - cloned from listing `111`
  - realtor phone set to `905014614767`
- Added Django Channels dependencies:
  - `channels`
  - `daphne`
- Fixed ASGI settings module from stale `Greenpastures.settings` to `coralcity.settings`.
- Added Channels routing and consumer:
  - `/ws/whatsapp/listing/<listing_id>/`
- Webhook and send endpoints now broadcast stored messages to listing-specific WebSocket groups.
- Widget now subscribes to listing WebSocket and spawns message bubbles instantly.
- Removed the widget's repeated HTTP polling loop; message updates now rely on webhook -> DB -> Channels, with one-shot refreshes only for initial load, reconnect recovery, and send fallback.
- Added a numbered unread badge on the floating WhatsApp button.
- Hardened webhook parsing for WAHA chat IDs sent as strings or `{ "_serialized": "..." }` objects.
- Added `WhatsAppIdentityAlias` so WAHA LID identities can map back to listing conversations.
- Added targeted WAHA LID lookup through `/api/<session>/lids/<lid>` for unknown inbound `@lid` messages.
- Added safe webhook/broadcast logs that report event, session, chat id, match count, and stored count without printing message text.
- Added Redis-backed Channels support through `REDIS_URL` or `CHANNEL_REDIS_URL`, with in-memory Channels kept as the local fallback.
- Removed `message.any` from the WAHA session webhook events so each WhatsApp message arrives once.
- Added a defensive Django webhook ignore for `message.any` in case an old WAHA config posts it again.
- Added LiteLLM-backed WhatsApp reply suggestions:
  - `POST /api/whatsapp/listing/<listing_id>/suggest`
  - composer magic button inserts a suggested draft into the input
  - settings support LiteLLM proxy mode through `WHATSAPP_AI_API_BASE`, `WHATSAPP_AI_API_KEY`, and `WHATSAPP_AI_MODEL`
  - tested against `https://aigw.whatsynaptic.com` with `moonshotai/kimi-k2.6`
  - empty conversations return a local starter prompt instead of asking the model to hallucinate from no chat context
- Verified WAHA authentication from `.env`:
  - `GET /api/server/status` returns `200`
  - `GET /api/sessions/user-905019481278` returns `200`
  - configured session is `WORKING`

## In Progress / Next

- Set `REDIS_URL` in deployed/multi-worker environments so webhook broadcasts and WebSocket consumers share the same channel layer.
- Add a listing-index conversation/notification panel that subscribes to an index WebSocket group.
- Track unread counts and last-message previews in the database.
- Improve WAHA webhook normalization using more of the TypeScript plugin logic as reference.
- Expand AI enrichment pipeline:
  - language detection
  - instant translation
  - persisted reply suggestions
  - conversation summaries
- Add background task execution for AI work so webhooks stay fast.

## Known Issues

- If a running Django process still returns WAHA `401 Unauthorized`, restart it so it reloads `.env` and the current `X-Api-Key` helper.
- Current channel layer is in-memory only; works for local/single-process testing, not production multi-worker deployment.
- Test listing `135` has no generated map embed, so its map iframe can 404 during local visual testing.

## Useful Test URLs

- Test listing:
  - `http://127.0.0.1:8000/en/listing/135/`
- Conversation API:
  - `http://127.0.0.1:8000/api/whatsapp/listing/135/conversation?sync=0`
- WebSocket:
  - `ws://127.0.0.1:8000/ws/whatsapp/listing/135/`
- WAHA webhook:
  - `http://127.0.0.1:8000/api/whatsapp/webhook`
