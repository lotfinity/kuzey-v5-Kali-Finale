import json
import re
import time
from datetime import datetime
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from listings.models import Listing
from realtors.models import Realtor


def clean_int(text):
    if text is None:
        return None
    if isinstance(text, (int, float)):
        return int(text)
    digits = re.findall(r"\d+", str(text))
    if not digits:
        return None
    return int("".join(digits))


def parse_date_iso(text):
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except Exception:
        return None


def format_phone(phones):
    if not phones or not isinstance(phones, list):
        return ""
    parts = []
    for p in phones:
        if not isinstance(p, dict):
            continue
        code = (p.get("areaCode") or "").strip()
        num = (p.get("phoneNumber") or "").strip()
        if code and num:
            parts.append(f"{code}{num}")
        elif num:
            parts.append(num)
    return ", ".join(parts)


class Command(BaseCommand):
    help = "Import hepsiemlak listings from the currently open Chrome tab via CDP."

    def add_arguments(self, parser):
        parser.add_argument("--realtor-id", type=int, default=1, help="Realtor ID")
        parser.add_argument(
            "--cdp-url",
            type=str,
            default="ws://100.74.113.44:9223/devtools/page/93046F94DA8CF42E810EF6819A56899A",
            help="CDP page WebSocket URL",
        )
        parser.add_argument("--dry-run", action="store_true", help="Parse only, do not save")
        parser.add_argument("--max-pages", type=int, default=1, help="Max pages to scrape (1-7)")

    def handle(self, *args, **options):
        cdp_url = options["cdp_url"]
        realtor_id = options["realtor_id"]
        dry_run = options["dry_run"]
        max_pages = options.get("max_pages", 1)

        realtor = Realtor.objects.filter(id=realtor_id).first()
        if not realtor:
            self.stderr.write(f"Realtor id={realtor_id} not found.")
            return

        import websocket

        all_listings = []

        for page_num in range(1, max_pages + 1):
            self.stdout.write(f"\n--- Page {page_num} ---")

            ws = websocket.create_connection(cdp_url, timeout=30)
            msg_id = 1

            def send(method, params=None):
                nonlocal msg_id
                req = {"id": msg_id, "method": method}
                if params:
                    req["params"] = params
                ws.send(json.dumps(req))
                msg_id += 1

            def recv():
                return json.loads(ws.recv())

            current_url = ""
            send("Runtime.evaluate", {
                "expression": "window.location.href",
                "returnByValue": True,
            })
            result = recv()
            current_url = result.get("result", {}).get("result", {}).get("value", "")
            self.stdout.write(f"Current URL: {current_url}")

            if page_num > 1:
                pagination_url = re.sub(r"p33=\d+", f"p33={page_num}", current_url)
                self.stdout.write(f"Navigating to page {page_num}: {pagination_url}")
                send("Page.navigate", {"url": pagination_url})
                nav_result = recv()
                err = nav_result.get("error", {})
                if err:
                    self.stdout.write(self.style.WARNING(f"Navigation error: {err.get('message')}"))
                time.sleep(2)

            send("Runtime.evaluate", {
                "expression": """
                (() => {
                    const d = window.__NUXT__;
                    if (!d || !d.data || !d.data[0]) return null;
                    return d.data[0];
                })()
                """,
                "returnByValue": True,
            })
            result = recv()
            data0 = result.get("result", {}).get("result", {}).get("value")

            if not data0:
                self.stdout.write(self.style.WARNING("No NUXT data found on this page"))
                ws.close()
                continue

            items = data0.get("list") or []
            self.stdout.write(f"Found {len(items)} listings on page {page_num}")

            for i, item in enumerate(items):
                listing_id = item.get("listingId")
                if not listing_id:
                    continue

                title = (item.get("title") or "").strip()
                price = item.get("price")
                if isinstance(price, str):
                    price = clean_int(price) or 0
                elif isinstance(price, (int, float)):
                    price = int(price)
                else:
                    price = 0

                currency = item.get("currency", "TRY")

                rooms_raw = item.get("roomAndLivingRoom")
                if isinstance(rooms_raw, list) and rooms_raw:
                    rooms_text = str(rooms_raw[0])
                else:
                    rooms_text = ""

                sqm = item.get("sqm") or {}
                m2_gross = None
                m2_net = None
                if isinstance(sqm, dict):
                    gs = sqm.get("grossSqm")
                    if isinstance(gs, list) and gs:
                        m2_gross = clean_int(gs[0])
                    elif isinstance(gs, (int, float)):
                        m2_gross = int(gs)
                    ns = sqm.get("netSqm")
                    if isinstance(ns, (int, float)):
                        m2_net = int(ns)

                city_obj = item.get("city") or {}
                county_obj = item.get("county") or {}
                district_obj = item.get("district") or {}

                def get_name(obj):
                    return obj.get("name", "") if isinstance(obj, dict) else (str(obj) if obj else "")

                city = get_name(city_obj)
                county = get_name(county_obj)
                district = get_name(district_obj)

                detail_url = item.get("detailUrl") or ""
                if detail_url and not detail_url.startswith("http"):
                    detail_url = "https://www.hepsiemlak.com/" + detail_url.lstrip("/")

                map_loc = item.get("mapLocation") or {}
                lat = None
                lon = None
                if isinstance(map_loc, dict):
                    lat = map_loc.get("lat")
                    lon = map_loc.get("lon")

                floor_obj = item.get("floor") or {}
                floor_name = floor_obj.get("name", "") if isinstance(floor_obj, dict) else ""
                floor_count = floor_obj.get("count") if isinstance(floor_obj, dict) else None

                create_date = parse_date_iso(item.get("startDate") or item.get("createDate"))

                sub_cat = item.get("subCategory") or {}
                property_type = sub_cat.get("typeName", "") if isinstance(sub_cat, dict) else ""
                if not property_type:
                    main_cat = item.get("mainCategory") or {}
                    property_type = main_cat.get("name", "") if isinstance(main_cat, dict) else ""

                image_url = item.get("imageUrl") or ""

                owner = item.get("owner") or {}
                phone = ""
                if isinstance(owner, dict):
                    phone = format_phone(owner.get("phones"))

                building_age = clean_int(item.get("age")) or None
                description = (item.get("detailDescription") or "").strip()

                record = {
                    "listing_id": listing_id,
                    "title": title,
                    "price": price,
                    "currency": currency,
                    "rooms_text": rooms_text,
                    "m2_gross": m2_gross,
                    "m2_net": m2_net,
                    "city": city,
                    "county": county,
                    "district": district,
                    "detail_url": detail_url,
                    "lat": lat,
                    "lon": lon,
                    "floor_name": floor_name,
                    "floor_count": floor_count,
                    "ad_date": create_date,
                    "property_type": property_type,
                    "image_url": image_url,
                    "phone": phone,
                    "building_age": building_age,
                    "description": description,
                }
                all_listings.append(record)
                self.stdout.write(f"  [{i}] {listing_id}: {title} - {price} {currency}")

            ws.close()

        self.stdout.write(f"\n=== Total listings extracted: {len(all_listings)} ===")

        if dry_run:
            self.stdout.write(f"DRY RUN: {len(all_listings)} listings would be created")
            for rec in all_listings:
                self.stdout.write(
                    f"  {rec['listing_id']}: {rec['title']} | {rec['price']} {rec['currency']} | "
                    f"{rec['city']}/{rec['county']}/{rec['district']} | {rec['detail_url']}"
                )
            return

        created = 0
        updated = 0
        skipped = 0

        for rec in all_listings:
            external_id = rec["listing_id"]
            if not external_id:
                skipped += 1
                continue

            existing = Listing.objects.filter(external_id=external_id).first()
            if existing:
                existing.price = rec["price"]
                existing.rooms_text = rec["rooms_text"] or existing.rooms_text
                if rec["m2_gross"]:
                    existing.m2_gross = rec["m2_gross"]
                    existing.sqft = int(round(rec["m2_gross"] * 10.7639))
                if rec["m2_net"]:
                    existing.m2_net = rec["m2_net"]
                fn = clean_int(rec["floor_name"])
                if fn is not None:
                    existing.floor_number = fn
                if rec["floor_count"] is not None:
                    existing.floors_total = rec["floor_count"]
                existing.original_url = rec["detail_url"] or existing.original_url
                if rec["lat"] and rec["lon"]:
                    if existing.latitude is None or existing.longitude is None:
                        existing.latitude = rec["lat"]
                        existing.longitude = rec["lon"]
                if rec["ad_date"] and not existing.ad_date:
                    existing.ad_date = rec["ad_date"].date() if isinstance(rec["ad_date"], datetime) else rec["ad_date"]
                if rec["phone"] and not existing.phone:
                    existing.phone = rec["phone"]
                if rec["building_age"] is not None and existing.building_age is None:
                    existing.building_age = rec["building_age"]
                if rec["description"] and not existing.description:
                    existing.description = rec["description"]
                existing.save(skip_geocode=True)
                updated += 1
                self.stdout.write(f"  Updated: {external_id}")
            else:
                sqft_val = 0
                if rec["m2_gross"]:
                    sqft_val = int(round(rec["m2_gross"] * 10.7639))

                listing = Listing(
                    realtor=realtor,
                    title=rec["title"],
                    address=rec["district"] or rec["county"] or "",
                    city=rec["city"],
                    state=rec["county"],
                    zipcode="",
                    description=rec["description"],
                    price=rec["price"],
                    bedrooms=rec["rooms_text"],
                    deal_type="satis",
                    property_type=rec["property_type"] or "Daire",
                    bathrooms=1,
                    sqft=sqft_val,
                    lot_size=Decimal("0.0"),
                    external_id=rec["listing_id"],
                    phone=rec["phone"],
                    ad_date=rec["ad_date"].date() if isinstance(rec["ad_date"], datetime) else rec["ad_date"],
                    original_url=rec["detail_url"],
                    m2_gross=rec["m2_gross"],
                    m2_net=rec["m2_net"],
                    rooms_text=rec["rooms_text"],
                    floor_number=clean_int(rec["floor_name"]),
                    floors_total=rec["floor_count"],
                    building_age=rec["building_age"],
                    source_batch_label=f"hepsiemlak_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                    source_search_context={
                        "source": "hepsiemlak",
                        "page_count": max_pages,
                        "imported_at": datetime.now().isoformat(),
                    },
                )
                if rec["lat"] and rec["lon"]:
                    listing.latitude = rec["lat"]
                    listing.longitude = rec["lon"]
                if rec["ad_date"]:
                    listing.list_date = rec["ad_date"]
                listing.save(skip_geocode=True)
                created += 1
                self.stdout.write(f"  Created: {external_id} - {rec['title']}")

        self.stdout.write(self.style.SUCCESS(
            f"Done. Created={created}, Updated={updated}, Skipped={skipped}"
        ))
