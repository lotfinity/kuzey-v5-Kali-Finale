# Kuzey Emlak — Project Seed Knowledge

## Business Purpose
A real estate investment platform targeting **medical tourism furnished rentals** in Istanbul. The strategy: buy small units (1+0, 1+1) near medical districts, furnish them, and rent short-term to medical tourists at Airbnb rates. The platform automates sourcing, analysis, owner outreach, and portfolio management.

## Medical Core Districts
Bagcilar, Bahcelievler, Bakirkoy, Kucukcekmece, Basaksehir, Sisli, Kadikoy, Atasehir, Esenyurt

## Current State (June 2026)

### What's Working
- ✅ Sahibinden.com listing import pipeline (Playwright + Android automation)
- ✅ Airbnb comparables fetching via Omkar Cloud API
- ✅ Rent calibration from nearby Airbnb comps
- ✅ Investment scoring with 3 scenarios (conservative/base/operator)
- ✅ Map with Airbnb layer toggle (Leaflet + MapLibre)
- ✅ WhatsApp integration via WAHA for owner contact
- ✅ 13-language i18n support
- ✅ Static site generation via django-distill
- ✅ Geocoding via Nominatim

### Recently Added (Last Session)
- ✅ Airbnb native map integration (replaced iframe approach)
- ✅ `fetch_airbnb_listings` / `fetch_airbnb_markets` management commands
- ✅ `calibrate_listing_rents` command (configurable radii, room-size matching)
- ✅ `score_investment_targets` command
- ✅ `listings/investor.py` — full scoring engine with portfolio builder
- ✅ MapLibre GL experimental map view
- ✅ Investor medical-rentals dashboard template

### Known Gaps & Next Steps
- ⏳ `django-extensions` not yet installed (install for `shell_plus`)
- ⏳ Many listings still need phone extraction
- ⏳ Rent calibration not yet applied (`--apply` flag needed)
- ⏳ Investment targets not yet scored for all districts
- ⏳ Owner outreach via WhatsApp not yet started at scale
- ⏳ Some listings missing coordinates (needs geocoding)
- ⏳ `MAINTENANCE_MODE` setting may block some views
- ⏳ Investor dashboard template exists but may need refinement

## Key Model Fields to Know

### Listing
- `price` (IntegerField) — sale price in TRY
- `estimated_monthly_rent_try` — calibrated rent estimate
- `airbnb_comp_count` / `airbnb_comp_median_try` — Airbnb market data
- `rentability_groups` — comma-separated investor tags
- `phone` — owner phone number
- `original_url` — source URL on Sahibinden
- `source_batch_label` — import batch identifier
- `latitude` / `longitude` — coordinates (nullable)

### AirbnbListing
- `listing_id` — unique Airbnb ID
- `total_cost` / `nightly_rate` — pricing data
- `overall_rating` / `review_count` — quality signals
- `latitude` / `longitude` — location for comp matching

### WhatsAppConversation / WhatsAppMessage
- Owner communication records linked to listings

## Investment Scoring Quick Reference
- **Conservative scenario**: 58% occupancy, lower revenue
- **Base scenario**: 72% occupancy, standard platform fees
- **Operator scenario**: 72%+12% uplift occupancy, 6% platform fee, 8% revenue uplift
- **Shortlist labels**: "Best buy now", "Best conservative fallback", "Needs negotiation", "Reject despite high Airbnb upside", "Watchlist"
- **Default budget**: 3,500,000 TRY (with 15% reserve)
- **Scoring weights**: ROI × 2.2 + comp_confidence × 0.22 + small_unit_bonus(14) + plan_b_coverage × 0.12 + network_confidence × 0.12 - legal_risk(18/10) - missing_data_penalty
