import json
import math
import statistics

from .models import AirbnbListing


DEFAULT_MAX_COMP_RADIUS_KM = 5
DEFAULT_PRIMARY_RADIUS_KM = 2
DEFAULT_FURNISHING_BUDGET = 120000
DEFAULT_CLOSING_BUFFER = 50000
DEFAULT_OPERATING_COST_RATE = 0.30


DEMAND_ANCHORS = [
    {
        "key": "tuyap",
        "title": "TUYAP Fair and Congress Center",
        "lat": 41.026546,
        "lng": 28.624144,
        "category": "Expo demand",
        "radius_km": 15,
        "reason": "Fair, congress, setup, exhibitor, and teardown demand can lift short-stay pricing.",
    },
    {
        "key": "marmara_park",
        "title": "Marmara Park",
        "lat": 41.003576,
        "lng": 28.659698,
        "category": "Retail and transport",
        "radius_km": 8,
        "reason": "Large mall and Metrobus-adjacent retail corridor for visitor convenience.",
    },
    {
        "key": "medicana_beylikduzu",
        "title": "Medicana International Istanbul",
        "lat": 41.013939,
        "lng": 28.646269,
        "category": "Medical demand",
        "radius_km": 10,
        "reason": "Private hospital demand can support patient-family and medical visitor stays.",
    },
    {
        "key": "metrobus_beylikduzu",
        "title": "Beylikduzu Metrobus Corridor",
        "lat": 41.001777,
        "lng": 28.641941,
        "category": "Transit",
        "radius_km": 8,
        "reason": "Metrobus access helps guests reach central Istanbul without a car.",
    },
]


TUYAP_EVENTS = [
    {"name": "Foodist Istanbul", "date": "01.09.2026 / 04.09.2026"},
    {"name": "Zuchex", "date": "09.09.2026 / 12.09.2026"},
    {"name": "Intermob", "date": "17.09.2026 / 20.09.2026"},
    {"name": "Fastener Expo Eurasia", "date": "17.09.2026 / 20.09.2026"},
    {"name": "Maktek Avrasya Fuari", "date": "28.09.2026 / 03.10.2026"},
    {"name": "Avrasya Ambalaj Istanbul Fuari", "date": "13.10.2026 / 16.10.2026"},
    {"name": "Woodtech", "date": "22.10.2026 / 25.10.2026"},
    {"name": "HOSTECH by TUSID ISTANBUL", "date": "10.11.2026 / 14.11.2026"},
    {"name": "Avrasya Cam / Pencere / Kapi 2026", "date": "21.11.2026 / 24.11.2026"},
    {"name": "Plast Eurasia Istanbul", "date": "02.12.2026 / 05.12.2026"},
    {"name": "Istanbul Kitap Fuari", "date": "12.12.2026 / 20.12.2026"},
]


def distance_km_between(lat1, lon1, lat2, lon2):
    radius_km = 6371.0088
    p1 = math.radians(float(lat1))
    p2 = math.radians(float(lat2))
    dp = math.radians(float(lat2) - float(lat1))
    dl = math.radians(float(lon2) - float(lon1))
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * radius_km * math.asin(math.sqrt(a))


def percent_value(values, percentile):
    values = sorted(values)
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    k = (len(values) - 1) * percentile
    low = math.floor(k)
    high = math.ceil(k)
    if low == high:
        return values[int(k)]
    return values[low] * (high - k) + values[high] * (k - low)


def airbnb_monthly_total(airbnb):
    if airbnb.total_cost is not None and airbnb.total_cost > 0:
        return float(airbnb.total_cost)
    if airbnb.nightly_rate is not None and airbnb.nightly_rate > 0:
        return float(airbnb.nightly_rate) * 30
    return None


def summarize_prices(comps):
    prices = sorted([item["monthly_total"] for item in comps if item.get("monthly_total")])
    if not prices:
        return {}
    return {
        "count": len(prices),
        "min": round(min(prices)),
        "p25": round(percent_value(prices, 0.25)),
        "median": round(statistics.median(prices)),
        "p75": round(percent_value(prices, 0.75)),
        "max": round(max(prices)),
        "average": round(statistics.mean(prices)),
    }


def listing_room_key(listing):
    raw = str(listing.rooms_text or listing.bedrooms or "").strip().lower()
    if raw.startswith("1+0") or "studio" in raw:
        return "studio"
    if raw.startswith("1+1") or raw == "1":
        return "1br"
    return raw or "unit"


def is_same_spec_comp(listing, airbnb):
    room_key = listing_room_key(listing)
    bedrooms = airbnb.bedroom_count
    if room_key == "studio":
        return bedrooms in (0, 1, None)
    if room_key == "1br":
        return bedrooms in (1, None)
    return True


def nearby_airbnb_cards(listing, max_radius_km=DEFAULT_MAX_COMP_RADIUS_KM, destination=None):
    qs = AirbnbListing.objects.exclude(latitude__isnull=True).exclude(longitude__isnull=True)
    if destination:
        qs = qs.filter(source_destination_query__iexact=destination)
    qs = qs.order_by("rank", "-overall_rating", "title")

    comps = []
    for item in qs:
        monthly_total = airbnb_monthly_total(item)
        if not monthly_total:
            continue
        distance = distance_km_between(listing.latitude, listing.longitude, item.latitude, item.longitude)
        if distance > max_radius_km:
            continue
        comps.append({
            "id": item.listing_id,
            "title": item.title,
            "property_type": item.property_type,
            "lat": float(item.latitude),
            "lng": float(item.longitude),
            "distance_km": round(distance, 2),
            "bedrooms": item.bedroom_count,
            "bathrooms": float(item.bathroom_count) if item.bathroom_count is not None else None,
            "beds": item.bed_count,
            "guest_capacity": item.guest_capacity,
            "photo": (item.photos or [""])[0] if item.photos else "",
            "nightly_rate": round(float(item.nightly_rate)) if item.nightly_rate is not None else None,
            "monthly_total": round(monthly_total),
            "nightly_equivalent": round(monthly_total / 30),
            "currency": item.currency or "TRY",
            "rating": float(item.overall_rating) if item.overall_rating is not None else None,
            "reviews": item.review_count or 0,
            "host_name": item.host_name,
            "host_review_count": item.host_review_count,
            "years_hosting": item.years_hosting,
            "is_superhost": item.is_superhost,
            "is_verified": item.is_verified,
            "is_guest_favorite": item.is_guest_favorite,
            "is_rare_find": item.is_rare_find,
            "is_available": item.is_available,
            "unavailability_reason": item.unavailability_reason,
            "url": item.booking_url or item.listing_url,
            "is_same_spec": is_same_spec_comp(listing, item),
            "source_destination_query": item.source_destination_query,
        })
    return sorted(comps, key=lambda item: item["distance_km"])


def primary_comp_set(comps, primary_radius_km=DEFAULT_PRIMARY_RADIUS_KM):
    comps_primary = [item for item in comps if item["distance_km"] <= primary_radius_km]
    same_spec_primary = [item for item in comps_primary if item["is_same_spec"]]
    same_spec_fallback = [item for item in comps if item["distance_km"] <= 3 and item["is_same_spec"]]
    return same_spec_primary or same_spec_fallback or comps_primary or comps


def select_micro_market_comps(comps, min_primary_comps=3):
    grouped = {}
    for comp in comps:
        key = comp.get("source_destination_query") or ""
        grouped.setdefault(key, []).append(comp)
    if len(grouped) <= 1:
        return comps, next(iter(grouped.keys()), "")

    ranked = []
    for key, group in grouped.items():
        primary = primary_comp_set(group)
        avg_distance = sum(item["distance_km"] for item in primary) / len(primary) if primary else 999
        ranked.append((len(primary), -avg_distance, key, group))
    ranked = sorted(ranked, reverse=True)
    best_count, _, best_key, best_group = ranked[0]
    if best_count >= min_primary_comps:
        return sorted(best_group, key=lambda item: item["distance_km"]), best_key
    return comps, ""


def nearby_demand_anchors(listing):
    anchors = []
    for anchor in DEMAND_ANCHORS:
        distance = distance_km_between(listing.latitude, listing.longitude, anchor["lat"], anchor["lng"])
        if distance <= anchor["radius_km"]:
            item = dict(anchor)
            item["distance_km"] = round(distance, 2)
            anchors.append(item)
    return sorted(anchors, key=lambda item: item["distance_km"])


def build_rentability(listing, price_summary):
    sale_price = int(listing.price or 0)
    airbnb_gross = price_summary.get("median") or int(listing.airbnb_comp_median_try or listing.estimated_monthly_rent_try or 0)
    airbnb_p75 = price_summary.get("p75") or airbnb_gross
    long_rent = int(listing.estimated_monthly_rent_try or round(airbnb_gross * 0.5))

    deployed_capital = sale_price + DEFAULT_FURNISHING_BUDGET + DEFAULT_CLOSING_BUFFER
    airbnb_net = round(airbnb_gross * (1 - DEFAULT_OPERATING_COST_RATE))
    operator_net = round(airbnb_p75 * (1 - DEFAULT_OPERATING_COST_RATE))
    long_net = round(long_rent * 0.90)

    def annual_roi(monthly_net):
        return round((monthly_net * 12 / deployed_capital) * 100, 1) if deployed_capital else 0

    return {
        "sale_price": sale_price,
        "furnishing_budget": DEFAULT_FURNISHING_BUDGET,
        "closing_buffer": DEFAULT_CLOSING_BUFFER,
        "operating_cost_rate": DEFAULT_OPERATING_COST_RATE,
        "deployed_capital": deployed_capital,
        "long_term_gross": long_rent,
        "long_term_net": long_net,
        "long_term_roi": annual_roi(long_net),
        "airbnb_gross": airbnb_gross,
        "airbnb_net": airbnb_net,
        "airbnb_roi": annual_roi(airbnb_net),
        "operator_gross": airbnb_p75,
        "operator_net": operator_net,
        "operator_roi": annual_roi(operator_net),
        "monthly_debt_free_payback_years": round(deployed_capital / (airbnb_net * 12), 1) if airbnb_net else None,
    }


def listing_image_urls(listing, limit=6):
    urls = []
    for image in listing.images.filter(is_visible=True).order_by("-is_primary", "order", "id")[:limit]:
        if image.image:
            urls.append(image.image.url)
    return urls


def build_listing_portfolio_context(listing, max_comp_radius_km=DEFAULT_MAX_COMP_RADIUS_KM, destination=None):
    comps = nearby_airbnb_cards(listing, max_radius_km=max_comp_radius_km, destination=destination)
    selected_destination = destination or ""
    if destination is None:
        comps, selected_destination = select_micro_market_comps(comps)
    primary_comps = primary_comp_set(comps)
    price_summary = summarize_prices(primary_comps)
    rentability = build_rentability(listing, price_summary)
    anchors = nearby_demand_anchors(listing)
    primary_anchor = anchors[0] if anchors else None
    has_tuyap = any(anchor["key"] == "tuyap" for anchor in anchors)

    if primary_anchor:
        hero_summary = (
            "%s investment unit near %s, priced for low capital entry and checked against nearby 30-night Airbnb comps."
            % (listing.rooms_text or listing.bedrooms or "Furnished", primary_anchor["title"])
        )
    else:
        hero_summary = (
            "%s investment unit checked against nearby 30-night Airbnb comps and local furnished-rental demand."
            % (listing.rooms_text or listing.bedrooms or "Furnished")
        )

    map_payload = {
        "listing": {
            "title": listing.title,
            "lat": float(listing.latitude),
            "lng": float(listing.longitude),
            "price": int(listing.price or 0),
            "rooms": listing.rooms_text or listing.bedrooms,
            "address": listing.address,
        },
        "anchors": anchors,
        "airbnb": comps[:20],
    }

    location_bullets = []
    for anchor in anchors[:4]:
        location_bullets.append("%s km from %s (%s)." % (anchor["distance_km"], anchor["title"], anchor["category"]))
    if primary_comps:
        location_bullets.append("%s nearby Airbnb comps support the 30-day rent model." % len(primary_comps))
    else:
        location_bullets.append("Nearby Airbnb comp data is thin; fetch fresh comps before treating this as final underwriting.")
    if listing_room_key(listing) in ("studio", "1br"):
        location_bullets.append("Small-unit format fits solo visitors, couples, business stays, and patient-family overflow.")
    if listing.floor_number or listing.floors_total:
        location_bullets.append(
            "Floor position: %s / %s."
            % (listing.floor_number or "n/a", listing.floors_total or "n/a")
        )

    return {
        "listing": listing,
        "listing_images": listing_image_urls(listing),
        "map_payload_json": json.dumps(map_payload, ensure_ascii=False),
        "airbnb_comps": comps[:12],
        "price_summary": price_summary,
        "rentability": rentability,
        "demand_anchors": anchors,
        "primary_anchor": primary_anchor,
        "selected_airbnb_destination": selected_destination,
        "hero_summary": hero_summary,
        "map_intro": (
            "The map plots the sale unit, nearby demand anchors, and Airbnb listings within %.1f km."
            % max_comp_radius_km
        ),
        "location_bullets": location_bullets,
        "demand_title": "TUYAP calendar pressure" if has_tuyap else "Strategic demand anchors",
        "demand_intro": (
            "Upcoming TUYAP Istanbul calendar items show repeated multi-day demand windows through the fair season."
            if has_tuyap
            else "Nearby demand anchors help explain whether the Airbnb comps are supported by repeatable guest traffic."
        ),
        "demand_events": TUYAP_EVENTS if has_tuyap else [],
        "demand_source_note": "Calendar source: official TUYAP fair calendar, checked July 4, 2026." if has_tuyap else "",
        "investment_read": build_investment_read(listing, rentability, primary_comps, anchors),
    }


def build_investment_read(listing, rentability, comps, anchors):
    if rentability["airbnb_roi"] >= 20:
        thesis = "The Airbnb base case is strong relative to deployed capital."
    elif rentability["airbnb_roi"] >= 12:
        thesis = "The Airbnb base case is workable, with negotiation and operating quality still important."
    else:
        thesis = "The current Airbnb base case needs caution or a lower purchase price."

    comp_note = (
        "%s primary comps give a usable starting point." % len(comps)
        if len(comps) >= 3
        else "Comp confidence is thin; refresh Airbnb data before committing."
    )
    anchor_note = (
        "Demand support comes from %s." % ", ".join(anchor["title"] for anchor in anchors[:3])
        if anchors
        else "No nearby strategic anchor was detected from the current anchor list."
    )
    return "%s %s %s Main risks are building rules, furnishing cost, review ramp-up, and seasonality." % (
        thesis,
        comp_note,
        anchor_note,
    )
