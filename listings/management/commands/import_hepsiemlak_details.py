import json
import re
import time
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import requests
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.db import close_old_connections

from listings.models import Listing, ListingImage


CDN_BASE = "https://hecdn01.hemlak.com"


def clean_int(val):
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return int(val)
    digits = re.findall(r"\d+", str(val))
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


def parse_bool(val, yes_vals=None):
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        s = val.strip().lower()
        if yes_vals:
            return s in yes_vals
        return s in ("yes", "evet", "var", "available", "true", "1")
    if isinstance(val, int):
        return val == 1
    return None


class Command(BaseCommand):
    help = "Import full details and images for hepsiemlak listings via CDP."

    def add_arguments(self, parser):
        parser.add_argument(
            "--cdp-url",
            type=str,
            default="ws://100.74.113.44:9223/devtools/page/93046F94DA8CF42E810EF6819A56899A",
            help="CDP page WebSocket URL",
        )
        parser.add_argument(
            "--batch-label",
            type=str,
            default="",
            help="Filter by source_batch_label prefix (default: all hepsiemlak listings)",
        )
        parser.add_argument("--delay", type=float, default=2.0, help="Seconds between listings")
        parser.add_argument("--dry-run", action="store_true", help="Parse only, do not save")
        parser.add_argument(
            "--listing-ids",
            type=str,
            default="",
            help="Comma-separated external_ids to process (overrides batch-label)",
        )
        parser.add_argument("--no-images", action="store_true", help="Skip image download")

    def handle(self, *args, **options):
        cdp_url = options["cdp_url"]
        delay = options["delay"]
        dry_run = options["dry_run"]
        no_images = options["no_images"]
        batch_label = options.get("batch_label", "")
        listing_ids_str = options.get("listing_ids", "")

        import websocket

        if listing_ids_str:
            ids = [x.strip() for x in listing_ids_str.split(",") if x.strip()]
            listings = Listing.objects.filter(external_id__in=ids)
            self.stdout.write(f"Processing {listings.count()} listings by explicit ids")
        elif batch_label:
            listings = Listing.objects.filter(source_batch_label__startswith=batch_label)
            self.stdout.write(f"Processing {listings.count()} listings with batch label '{batch_label}'")
        else:
            listings = Listing.objects.filter(source_batch_label__startswith="hepsiemlak_")
            self.stdout.write(f"Processing {listings.count()} listings with 'hepsiemlak_' batch label")

        if not listings:
            self.stdout.write(self.style.WARNING("No listings found."))
            return

        image_base_url = "https://www.hepsiemlak.com"

        updated = 0
        skipped = 0
        total_images = 0
        total_listings = listings.count()

        for idx, listing in enumerate(listings, start=1):
            ext_id = listing.external_id
            detail_url = listing.original_url or f"{image_base_url}/en/..."
            self.stdout.write(f"\n[{idx}/{total_listings}] {ext_id}: {listing.title}")

            if not detail_url or "hepsiemlak" not in detail_url:
                self.stdout.write(self.style.WARNING(f"  SKIP: no hepsiemlak URL for {ext_id}"))
                skipped += 1
                continue

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

            # Navigate to detail page
            send("Page.navigate", {"url": detail_url})
            nav_result = recv()
            err = nav_result.get("error", {})
            if err:
                self.stdout.write(self.style.WARNING(f"  Navigation error: {err.get('message')}"))
                ws.close()
                skipped += 1
                continue

            # Wait for the page to fully load
            send("Page.waitForLoadEvent", {"eventName": "load"})
            recv()
            # Extra settle time for JS rendering
            time.sleep(1.5)

            # Check if we got NUXT data (with retries)
            data0 = None
            for attempt in range(3):
                send("Runtime.evaluate", {
                    "expression": """
                    (() => {
                        try {
                            const d = window.__NUXT__;
                            if (!d || !d.data || !d.data[0]) return null;
                            return d.data[0];
                        } catch(e) { return null; }
                    })()
                    """,
                    "returnByValue": True,
                })
                result = recv()
                data0 = result.get("result", {}).get("result", {}).get("value")
                if data0 and data0.get("detailData"):
                    break
                if attempt < 2:
                    time.sleep(2)

            if not data0 or not data0.get("detailData"):
                self.stdout.write(self.style.WARNING(f"  No NUXT data for {ext_id} after retries"))
                ws.close()
                skipped += 1
                continue

            dd = data0.get("detailData") or {}

            if dry_run:
                self.stdout.write(f"  DRY RUN: would update {ext_id}")
                ws.close()
                continue

            # --- Update listing fields ---
            changed = False

            price_val = dd.get("price")
            if isinstance(price_val, (int, float)) and price_val > 0 and listing.price != int(price_val):
                listing.price = int(price_val)
                changed = True

            title_val = (dd.get("title") or "").strip()
            if title_val and title_val != listing.title:
                listing.title = title_val
                changed = True

            desc_val = (dd.get("detailDescription") or "").strip()
            if desc_val and desc_val != listing.description:
                listing.description = desc_val
                changed = True

            rooms = dd.get("roomAndLivingRoom")
            if isinstance(rooms, list) and rooms:
                rt = str(rooms[0])
                if rt != listing.rooms_text:
                    listing.rooms_text = rt
                    listing.bedrooms = rt
                    changed = True

            sqm = dd.get("sqm") or {}
            if isinstance(sqm, dict):
                gs = sqm.get("grossSqm")
                ns = sqm.get("netSqm")
                if isinstance(gs, list) and gs:
                    v = clean_int(gs[0]) or 0
                    if v and v != listing.m2_gross:
                        listing.m2_gross = v
                        listing.sqft = int(round(v * 10.7639))
                        changed = True
                elif isinstance(gs, (int, float)):
                    v = int(gs)
                    if v and v != listing.m2_gross:
                        listing.m2_gross = v
                        listing.sqft = int(round(v * 10.7639))
                        changed = True
                if isinstance(ns, (int, float)):
                    v = int(ns)
                    if v and v != listing.m2_net:
                        listing.m2_net = v
                        changed = True

            floor_obj = dd.get("floor") or {}
            if isinstance(floor_obj, dict):
                fn = floor_obj.get("name", "")
                if fn:
                    fn_int = clean_int(fn)
                    if fn_int is not None and fn_int != listing.floor_number:
                        listing.floor_number = fn_int
                        changed = True
                fc = floor_obj.get("count")
                if fc is not None and fc != listing.floors_total:
                    listing.floors_total = fc
                    changed = True

            building_age = dd.get("age")
            if building_age is not None:
                ba = clean_int(building_age)
                if ba is not None and ba != listing.building_age:
                    listing.building_age = ba
                    changed = True

            heating_obj = dd.get("heating") or {}
            if isinstance(heating_obj, dict):
                hn = heating_obj.get("name", "")
                if hn and hn != listing.heating:
                    listing.heating = hn
                    changed = True

            furnished_val = dd.get("furnished")
            if furnished_val is not None:
                fb = parse_bool(furnished_val)
                if fb is not None and fb != listing.furnished:
                    listing.furnished = fb
                    changed = True

            balcony_val = dd.get("balcony")
            if balcony_val is not None and isinstance(balcony_val, dict):
                bn = balcony_val.get("name", "")
                if bn and bn != listing.balcony:
                    listing.balcony = bn
                    changed = True
            elif isinstance(balcony_val, str):
                if balcony_val and balcony_val != listing.balcony:
                    listing.balcony = balcony_val
                    changed = True

            parking_val = dd.get("parking")
            if parking_val is not None and isinstance(parking_val, dict):
                pn = parking_val.get("name", "")
                if pn and pn != listing.parking_area:
                    listing.parking_area = pn
                    changed = True
            elif isinstance(parking_val, str):
                if parking_val and parking_val != listing.parking_area:
                    listing.parking_area = parking_val
                    changed = True

            bath_val = dd.get("bathRoom")
            if bath_val is not None:
                bi = clean_int(bath_val)
                if bi is not None and bi != listing.bathrooms:
                    listing.bathrooms = bi
                    changed = True

            map_loc = dd.get("mapLocation") or {}
            if isinstance(map_loc, dict):
                lat = map_loc.get("lat")
                lon = map_loc.get("lon")
                if lat and lon:
                    if listing.latitude is None or listing.longitude is None:
                        listing.latitude = lat
                        listing.longitude = lon
                        changed = True

            city_obj = dd.get("city") or {}
            county_obj = dd.get("county") or {}

            def get_name(obj):
                return obj.get("name", "") if isinstance(obj, dict) else (str(obj) if obj else "")

            city_name = get_name(city_obj)
            county_name = get_name(county_obj)

            if city_name and city_name != listing.city:
                listing.city = city_name
                changed = True
            if county_name and county_name != listing.state:
                listing.state = county_name
                changed = True

            usage_obj = dd.get("usage") or {}
            if isinstance(usage_obj, dict):
                un = usage_obj.get("name", "")
                if un and un != listing.usage_status:
                    listing.usage_status = un
                    changed = True

            deed = dd.get("registerState")
            if deed and isinstance(deed, str) and deed != listing.deed_status:
                listing.deed_status = deed
                changed = True

            sides = dd.get("sides") or []
            if isinstance(sides, list) and sides:
                side_names = [s.get("name", "") for s in sides if isinstance(s, dict) and s.get("name")]
                if side_names:
                    side_str = ", ".join(side_names)
                    if side_str and side_str != getattr(listing, "description", ""):
                        pass

            in_complex = dd.get("housingComplex")
            if isinstance(in_complex, dict):
                ic_name = in_complex.get("name", "")
                if ic_name:
                    listing.in_complex = parse_bool(ic_name.lower() in ("yes", "evet", "var"))
                    changed = True
                    if ic_name.lower() not in ("yes", "no", "evet", "hayır", "hayir", "var", "yok"):
                        listing.complex_name = ic_name
                        changed = True

            maintenance_fee = dd.get("fee")
            if maintenance_fee is not None:
                mf = clean_int(maintenance_fee)
                if mf is not None and mf != listing.maintenance_fee:
                    listing.maintenance_fee = mf
                    changed = True

            deposit_val = dd.get("deposit") or {}
            if isinstance(deposit_val, dict):
                dep_amount = deposit_val.get("amount")
                if dep_amount is not None:
                    da = clean_int(dep_amount)
                    if da is not None and da != listing.deposit:
                        listing.deposit = da
                        changed = True

            from_whom = dd.get("advertiseOwner") or ""
            if from_whom and isinstance(from_whom, str) and from_whom != listing.from_whom:
                listing.from_whom = from_whom
                changed = True

            # Extract breadcrumbs for address
            breadcrumbs = data0.get("breadcrumbs") or []
            if isinstance(breadcrumbs, list) and breadcrumbs:
                crumbs = [b.get("name", "") for b in breadcrumbs if isinstance(b, dict) and b.get("name")]
                if crumbs:
                    pass

            ad_date_str = dd.get("startDate") or dd.get("createdDate")
            if ad_date_str:
                ad_date = parse_date_iso(ad_date_str)
                if ad_date and not listing.ad_date:
                    listing.ad_date = ad_date.date() if hasattr(ad_date, 'date') else ad_date
                    changed = True
                if ad_date and not listing.list_date:
                    listing.list_date = ad_date
                    changed = True

            if changed:
                listing.save(skip_geocode=True)
                self.stdout.write(f"  Updated listing fields")
            else:
                self.stdout.write(f"  No field changes needed")

            # --- Process images ---
            if not no_images:
                image_items = data0.get("image") or dd.get("images") or []
                if isinstance(image_items, list) and image_items:
                    self._import_images(listing, image_items, ext_id)
                    total_images += len(image_items)
                    self.stdout.write(f"  Processed {len(image_items)} images")
                else:
                    self.stdout.write(f"  No images found")
            else:
                self.stdout.write(f"  Images skipped (--no-images)")

            updated += 1
            ws.close()

            if delay > 0:
                time.sleep(delay)

        self.stdout.write(self.style.SUCCESS(
            f"\nDone. Updated={updated}, Skipped={skipped}, Total images processed={total_images}"
        ))

    def _import_images(self, listing, image_items, ext_id):
        existing_count = listing.images.count()
        existing_urls = set()
        for img in listing.images.all():
            try:
                existing_urls.add(img.image.name)
            except Exception:
                pass

        sess = requests.Session()
        sess.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
            "Accept": "image/avif,image/webp,image/*,*/*;q=0.8",
            "Referer": "https://www.hepsiemlak.com/",
        })

        added = 0
        for i, img_item in enumerate(image_items):
            if isinstance(img_item, str):
                img_path = img_item
            elif isinstance(img_item, dict):
                img_path = img_item.get("url") or img_item.get("path") or ""
            else:
                continue

            if not img_path:
                continue

            if img_path.startswith("http"):
                img_url = img_path
            else:
                img_path = img_path.lstrip("/")
                img_url = f"{CDN_BASE}/{img_path}"

            fname = f"hepsiemlak_{ext_id}_{i:03d}.jpg"

            if fname in existing_urls:
                continue

            try:
                r = sess.get(img_url, timeout=20)
                if r.status_code == 200 and r.content:
                    img = ListingImage(
                        listing=listing,
                        order=i,
                        is_primary=(i == 0),
                        is_visible=True,
                    )
                    img.image.save(fname, ContentFile(r.content), save=True)
                    added += 1
                else:
                    self.stdout.write(f"    Failed to download image {i}: HTTP {r.status_code}")
            except Exception as e:
                self.stdout.write(f"    Image download error for {i}: {e}")

        if added:
            self.stdout.write(f"    Added {added} new images")
