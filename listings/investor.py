import itertools
import math
import re
from statistics import median

from django.db.models import Max, Min

from .models import AirbnbListing, Listing


MEDICAL_CORE_DISTRICTS = [
    "Bagcilar",
    "Bahcelievler",
    "Bakirkoy",
    "Kucukcekmece",
    "Basaksehir",
    "Sisli",
    "Kadikoy",
    "Atasehir",
    "Esenyurt",
]


DEFAULT_INVESTOR_SETTINGS = {
    "budget": 3500000,
    "reserve_percent": 15,
    "furnishing_per_unit": 175000,
    "legal_buffer_per_unit": 50000,
    "platform_fee_percent": 15,
    "management_fee_percent": 10,
    "monthly_utilities": 4500,
    "monthly_cleaning": 3500,
    "monthly_maintenance_percent": 1.0,
    "base_occupancy_percent": 72,
    "conservative_occupancy_percent": 58,
    "operator_occupancy_uplift_percent": 12,
    "operator_platform_fee_percent": 6,
    "operator_revenue_uplift_percent": 8,
    "private_network_confidence_percent": 70,
    "plan_b_rent_factor_percent": 55,
    "max_comp_radius_km": 5,
    "min_comps": 3,
}


INVESTOR_SETTING_LIMITS = {
    "budget": (1000000, 10000000),
    "reserve_percent": (5, 30),
    "furnishing_per_unit": (75000, 300000),
    "legal_buffer_per_unit": (25000, 250000),
    "base_occupancy_percent": (40, 90),
    "conservative_occupancy_percent": (30, 80),
    "operator_occupancy_uplift_percent": (0, 25),
    "operator_revenue_uplift_percent": (0, 25),
    "private_network_confidence_percent": (0, 100),
    "plan_b_rent_factor_percent": (35, 85),
    "max_comp_radius_km": (1, 15),
}


def clamp(value, minimum, maximum):
    return max(minimum, min(maximum, value))


def parse_int(value, default):
    try:
        return int(float(str(value).replace(",", "").strip()))
    except (TypeError, ValueError):
        return default


def parse_float(value, default):
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return default


def investor_settings_from_request(request):
    settings = dict(DEFAULT_INVESTOR_SETTINGS)
    if request is None:
        return settings
    numeric_keys = set(settings.keys())
    for key in numeric_keys:
        if key in request.GET:
            current = settings[key]
            if isinstance(current, int):
                settings[key] = parse_int(request.GET.get(key), current)
            else:
                settings[key] = parse_float(request.GET.get(key), current)
            if key in INVESTOR_SETTING_LIMITS:
                minimum, maximum = INVESTOR_SETTING_LIMITS[key]
                settings[key] = clamp(settings[key], minimum, maximum)
    return settings


def valid_coord(lat, lng):
    try:
        latf = float(lat)
        lngf = float(lng)
    except (TypeError, ValueError):
        return False
    return -90 <= latf <= 90 and -180 <= lngf <= 180 and not (latf == 0 and lngf == 0)


def distance_km(lat1, lng1, lat2, lng2):
    radius = 6371.0088
    phi1 = math.radians(float(lat1))
    phi2 = math.radians(float(lat2))
    d_phi = math.radians(float(lat2) - float(lat1))
    d_lam = math.radians(float(lng2) - float(lng1))
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lam / 2) ** 2
    return radius * (2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)))


def percentile(values, pct):
    if not values:
        return 0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, int(round((pct / 100) * (len(ordered) - 1)))))
    return ordered[idx]


def room_size_from_listing(listing):
    raw = str(listing.rooms_text or listing.bedrooms or "").lower().replace(" ", "")
    match = re.search(r"\d+\+\d+", raw)
    return match.group(0) if match else ""


def room_size_from_airbnb(airbnb):
    bedrooms = airbnb.bedroom_count or 0
    if bedrooms <= 0:
        return "1+0"
    return "%s+1" % bedrooms


def monthly_airbnb_price(airbnb):
    if airbnb.total_cost is not None and airbnb.total_cost > 0:
        return float(airbnb.total_cost)
    if airbnb.nightly_rate is not None and airbnb.nightly_rate > 0:
        return float(airbnb.nightly_rate) * 30
    return 0


def listing_photo_url(listing):
    try:
        image = listing.images.order_by("order", "id").first()
        if image and image.image:
            return image.image.url
    except Exception:
        return ""
    return ""


def airbnb_comp_records():
    records = []
    qs = AirbnbListing.objects.exclude(latitude__isnull=True).exclude(longitude__isnull=True)
    for item in qs:
        if not valid_coord(item.latitude, item.longitude):
            continue
        monthly = monthly_airbnb_price(item)
        if monthly <= 0:
            continue
        records.append(
            {
                "id": item.listing_id,
                "title": item.title,
                "lat": float(item.latitude),
                "lng": float(item.longitude),
                "room_size": room_size_from_airbnb(item),
                "monthly": monthly,
                "rating": float(item.overall_rating) if item.overall_rating is not None else None,
                "reviews": item.review_count or 0,
                "rank": item.rank,
                "destination": item.source_destination_query,
                "url": item.booking_url or item.listing_url,
            }
        )
    return records


def nearby_airbnb_comps(listing, comps, settings):
    if not valid_coord(listing.latitude, listing.longitude):
        return []
    room_size = room_size_from_listing(listing)
    max_radius = float(settings["max_comp_radius_km"])
    matched = []
    fallback = []
    for comp in comps:
        dist = distance_km(listing.latitude, listing.longitude, comp["lat"], comp["lng"])
        if dist > max_radius:
            continue
        record = dict(comp)
        record["distance_km"] = dist
        fallback.append(record)
        if room_size and comp["room_size"] == room_size:
            matched.append(record)
    chosen = matched if len(matched) >= int(settings["min_comps"]) else fallback
    return sorted(chosen, key=lambda item: item["distance_km"])


def monthly_net(gross, price, settings, scenario):
    occupancy = settings["base_occupancy_percent"] / 100
    platform_fee = settings["platform_fee_percent"] / 100
    revenue_multiplier = 1.0
    if scenario == "conservative":
        occupancy = settings["conservative_occupancy_percent"] / 100
    elif scenario == "operator":
        occupancy = min(0.95, occupancy + settings["operator_occupancy_uplift_percent"] / 100)
        platform_fee = settings["operator_platform_fee_percent"] / 100
        revenue_multiplier += settings["operator_revenue_uplift_percent"] / 100
    occupied_revenue = gross * occupancy * revenue_multiplier
    fees = occupied_revenue * platform_fee
    management = occupied_revenue * (settings["management_fee_percent"] / 100)
    maintenance = price * (settings["monthly_maintenance_percent"] / 100) / 12
    fixed = settings["monthly_utilities"] + settings["monthly_cleaning"] + maintenance
    return round(occupied_revenue - fees - management - fixed)


def score_listing(listing, comps, settings):
    sale_price = int(listing.price or 0)
    setup_cost = int(settings["furnishing_per_unit"] + settings["legal_buffer_per_unit"])
    total_deployed = sale_price + setup_cost
    room_size = room_size_from_listing(listing)
    nearby = nearby_airbnb_comps(listing, comps, settings)
    comp_prices = [item["monthly"] for item in nearby]
    if comp_prices:
        comp_median = round(median(comp_prices))
        comp_p75 = round(percentile(comp_prices, 75))
    else:
        comp_median = int(listing.estimated_rent or 0)
        comp_p75 = comp_median
    plan_b = round(comp_median * (settings["plan_b_rent_factor_percent"] / 100))

    scenarios = {}
    for scenario in ("conservative", "base", "operator"):
        gross = comp_median if scenario != "operator" else comp_p75
        net = monthly_net(gross, sale_price, settings, scenario)
        annual_net = net * 12
        roi = (annual_net / total_deployed * 100) if total_deployed else 0
        payback = (total_deployed / annual_net) if annual_net > 0 else None
        scenarios[scenario] = {
            "gross_monthly": round(gross),
            "net_monthly": round(net),
            "annual_net": round(annual_net),
            "roi_percent": round(roi, 2),
            "payback_years": round(payback, 1) if payback else None,
        }

    comp_confidence = min(100, len(nearby) * 18)
    if len(nearby) < int(settings["min_comps"]):
        comp_confidence = max(15, comp_confidence - 15)
    small_unit_bonus = 14 if room_size in ("1+0", "1+1") else 0
    plan_b_coverage = min(100, (plan_b / max(1, settings["monthly_utilities"] + settings["monthly_cleaning"])) * 18)
    network_confidence = settings["private_network_confidence_percent"]
    legal_risk_penalty = 18 if not listing.in_complex else 10
    missing_data_penalty = 0
    if not valid_coord(listing.latitude, listing.longitude):
        missing_data_penalty += 25
    if not listing.phone:
        missing_data_penalty += 5
    if not listing.original_url:
        missing_data_penalty += 5
    risk_adjusted = (
        scenarios["operator"]["roi_percent"] * 2.2
        + comp_confidence * 0.22
        + small_unit_bonus
        + plan_b_coverage * 0.12
        + network_confidence * 0.12
        - legal_risk_penalty
        - missing_data_penalty
    )

    if scenarios["operator"]["roi_percent"] >= 18 and comp_confidence >= 45:
        shortlist = "Best buy now"
    elif scenarios["base"]["roi_percent"] >= 12 and plan_b >= 18000:
        shortlist = "Best conservative fallback"
    elif scenarios["operator"]["roi_percent"] >= 15 and comp_confidence < 45:
        shortlist = "Needs negotiation"
    elif comp_median > 0 and scenarios["conservative"]["net_monthly"] <= 0:
        shortlist = "Reject despite high Airbnb upside"
    else:
        shortlist = "Watchlist"

    reasons = []
    if room_size in ("1+0", "1+1"):
        reasons.append("Small-unit format fits flexible furnished stays.")
    if len(nearby) >= int(settings["min_comps"]):
        reasons.append("Nearby Airbnb comps support the revenue estimate.")
    else:
        reasons.append("Comp count is thin; verify with fresh Airbnb/Sahibinden data.")
    if plan_b >= 18000:
        reasons.append("Plan-B monthly rent gives downside coverage.")
    if settings["operator_occupancy_uplift_percent"] > 0:
        reasons.append("Operator upside reflects direct medical/referral demand.")

    return {
        "id": listing.id,
        "title": listing.title,
        "price": sale_price,
        "total_deployed": round(total_deployed),
        "setup_cost": setup_cost,
        "room_size": room_size,
        "city": listing.city,
        "state": listing.state,
        "address": listing.address,
        "lat": listing.latitude,
        "lng": listing.longitude,
        "photo_url": listing_photo_url(listing),
        "phone": listing.phone,
        "source_url": listing.original_url,
        "source_batch_label": listing.source_batch_label,
        "comp_count": len(nearby),
        "comp_median": comp_median,
        "comp_p75": comp_p75,
        "plan_b_monthly": plan_b,
        "comp_confidence": round(comp_confidence),
        "risk_adjusted_score": round(risk_adjusted, 1),
        "shortlist": shortlist,
        "scenarios": scenarios,
        "nearest_comps": nearby[:5],
        "reasons": reasons,
        "due_diligence": [
            "Tapu/title status",
            "Real aidat and building debts",
            "Furnished rental permission and building rules",
            "Guest access/security practicality",
            "Utilities/meters and internet readiness",
            "Furnishing/renovation estimate",
            "Plan-B monthly rent validation",
            "Seller/agent phone and source URL",
            "Medical-demand access and transport",
            "Can work via direct network, not Airbnb only",
        ],
    }


def build_portfolios(scored, settings, max_units=3):
    purchase_budget = settings["budget"] * (1 - settings["reserve_percent"] / 100)
    eligible = [item for item in scored if item["total_deployed"] <= purchase_budget]
    portfolios = []
    for size in range(1, max_units + 1):
        for combo in itertools.combinations(eligible, size):
            deployed = sum(item["total_deployed"] for item in combo)
            if deployed > purchase_budget:
                continue
            net = sum(item["scenarios"]["operator"]["net_monthly"] for item in combo)
            annual = net * 12
            roi = annual / deployed * 100 if deployed else 0
            confidence = sum(item["comp_confidence"] for item in combo) / len(combo)
            score = roi * 2 + confidence * 0.15 + len(combo) * 2
            portfolios.append(
                {
                    "label": "%s unit%s" % (size, "" if size == 1 else "s"),
                    "listing_ids": [item["id"] for item in combo],
                    "titles": [item["title"] for item in combo],
                    "deployed": round(deployed),
                    "remaining_budget": round(purchase_budget - deployed),
                    "operator_net_monthly": round(net),
                    "annual_net": round(annual),
                    "roi_percent": round(roi, 2),
                    "confidence": round(confidence),
                    "score": round(score, 1),
                }
            )
    return sorted(portfolios, key=lambda item: item["score"], reverse=True)[:10]


def source_gap_suggestions(scored, settings):
    affordable = [item for item in scored if item["total_deployed"] <= settings["budget"]]
    strong = [item for item in affordable if item["shortlist"] in ("Best buy now", "Best conservative fallback")]
    suggestions = []
    if len(strong) < 5:
        suggestions.append(
            {
                "title": "Search more medical-core small units",
                "brief": "Sahibinden filters: Bagcilar, Bahcelievler, Bakirkoy, Kucukcekmece, Basaksehir; 1+0 or 1+1; price below reserve-adjusted budget; residence or easy guest-access buildings.",
                "commands": [
                    "rtk venv/bin/python manage.py sync_android_missing_listings --max-pages 10 --batch-label medical-core-small-units",
                    "rtk venv/bin/python manage.py sync_android_listing_phones --details --max-pages 10",
                    "rtk venv/bin/python manage.py sync_android_listing_images --max-pages 10",
                    "rtk venv/bin/python manage.py score_investment_targets",
                ],
            }
        )
    if any(item["comp_confidence"] < 45 for item in scored[:10]):
        suggestions.append(
            {
                "title": "Improve Airbnb comp confidence",
                "brief": "Fetch more Airbnb pages around the districts that appear in the top 10 but have thin comp counts.",
                "commands": [
                    "rtk venv/bin/python manage.py fetch_airbnb_markets --pages 2 --call-budget 60",
                    "rtk venv/bin/python manage.py score_investment_targets",
                ],
            }
        )
    if not suggestions:
        suggestions.append(
            {
                "title": "Move to due diligence",
                "brief": "The current shortlist is strong enough to verify tapu, aidat, building rules, furnishing cost, and direct-rental feasibility.",
                "commands": [],
            }
        )
    return suggestions


def build_investor_summary(settings=None, limit=120):
    settings = dict(DEFAULT_INVESTOR_SETTINGS if settings is None else settings)
    comps = airbnb_comp_records()
    listings = Listing.objects.filter(is_published=True).order_by("-list_date", "id")[:limit]
    scored = [score_listing(listing, comps, settings) for listing in listings]
    scored = sorted(scored, key=lambda item: item["risk_adjusted_score"], reverse=True)
    agg = Listing.objects.filter(is_published=True).aggregate(price_min=Min("price"), price_max=Max("price"))
    return {
        "settings": settings,
        "market": {
            "sale_listing_count": Listing.objects.filter(is_published=True).count(),
            "airbnb_comp_count": len(comps),
            "medical_core_districts": MEDICAL_CORE_DISTRICTS,
            "price_min": agg["price_min"] or 0,
            "price_max": agg["price_max"] or 0,
        },
        "kpis": {
            "best_operator_roi": scored[0]["scenarios"]["operator"]["roi_percent"] if scored else 0,
            "best_net_monthly": scored[0]["scenarios"]["operator"]["net_monthly"] if scored else 0,
            "strong_shortlist_count": len([item for item in scored if item["shortlist"] in ("Best buy now", "Best conservative fallback")]),
            "thin_comp_count": len([item for item in scored if item["comp_confidence"] < 45]),
        },
        "ranked": scored,
        "portfolios": build_portfolios(scored, settings),
        "sourcing": source_gap_suggestions(scored, settings),
    }
