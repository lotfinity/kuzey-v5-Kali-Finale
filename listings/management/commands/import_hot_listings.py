import json
import re
from datetime import datetime

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from listings.models import Listing
from realtors.models import Realtor


def parse_int(value):
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    cleaned = re.sub(r"[^0-9-]", "", text)
    if cleaned in {"", "-"}:
        return None
    try:
        return int(cleaned)
    except ValueError:
        return None


def parse_price(value):
    result = parse_int(value)
    if result is None:
        return 0
    return result


def parse_date(value):
    if not value:
        return None
    text = str(value).strip()
    for fmt in ["%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y"]:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def normalize_deal_type(value):
    if not value:
        return "satis"
    text = str(value).strip().lower()
    if any(token in text for token in ["for rent", "kiralık", "kiralik", "rent"]):
        return "kiralik"
    if any(token in text for token in ["for sale", "satılık", "satilik", "sale"]):
        return "satis"
    return "satis"


def parse_rooms(value):
    if not value:
        return None
    text = str(value).strip()
    if match := re.search(r"(\d+)\s*\+\s*\d+", text):
        return int(match.group(1))
    if match := re.search(r"(\d+)", text):
        return int(match.group(1))
    return None


def parse_address(address):
    if not address:
        return "", "", ""
    parts = [part.strip() for part in str(address).split(",") if part.strip()]
    if len(parts) >= 3:
        return str(address).strip(), parts[0], parts[1]
    if len(parts) == 2:
        return str(address).strip(), parts[0], parts[1]
    if len(parts) == 1:
        return str(address).strip(), parts[0], ""
    return str(address).strip(), "", ""


def build_original_url(listing_no):
    if not listing_no:
        return ""
    listing_no_str = str(listing_no).strip()
    if listing_no_str.isdigit():
        return f"https://www.sahibinden.com/ilan/{listing_no_str}"
    return ""


class Command(BaseCommand):
    help = "Import hot listings from a JSON export into the Listing model."

    def add_arguments(self, parser):
        parser.add_argument(
            "json_path",
            type=str,
            help="Path to the JSON file containing the listings",
        )
        parser.add_argument(
            "--realtor-id",
            type=int,
            required=True,
            help="Realtor ID to assign to imported listings",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Validate and summarize without saving to the database",
        )
        parser.add_argument(
            "--update-existing",
            action="store_true",
            help="Update existing records when external_id matches",
        )
        parser.add_argument(
            "--source-status-ok-only",
            action="store_true",
            help="Import only JSON entries whose status is 'ok'",
        )
        parser.add_argument(
            "--source-batch-label",
            default="",
            help="Optional label for the sourcing/import batch that produced these listings",
        )
        parser.add_argument(
            "--source-search-context-json",
            default="",
            help="Optional JSON object describing the manual Sahibinden search context",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        json_path = options["json_path"]
        realtor_id = options["realtor_id"]
        dry_run = options["dry_run"]
        update_existing = options["update_existing"]
        ok_only = options["source_status_ok_only"]
        source_batch_label = str(options["source_batch_label"] or "").strip()
        source_search_context = {}
        if options["source_search_context_json"]:
            try:
                source_search_context = json.loads(options["source_search_context_json"])
            except json.JSONDecodeError as exc:
                raise CommandError(f"Invalid --source-search-context-json: {exc}") from exc
            if not isinstance(source_search_context, dict):
                raise CommandError("--source-search-context-json must decode to a JSON object")

        try:
            realtor = Realtor.objects.get(id=realtor_id)
        except Realtor.DoesNotExist:
            raise CommandError(f"Realtor with id={realtor_id} not found")

        try:
            with open(json_path, encoding="utf-8") as fp:
                data = json.load(fp)
        except FileNotFoundError:
            raise CommandError(f"JSON file not found: {json_path}")
        except json.JSONDecodeError as exc:
            raise CommandError(f"Invalid JSON file: {exc}") from exc

        if not isinstance(data, list):
            raise CommandError("Expected JSON top-level value to be a list of listings")

        created = 0
        updated = 0
        skipped = 0

        for idx, item in enumerate(data, start=1):
            if not isinstance(item, dict):
                self.stdout.write(self.style.WARNING(f"Skipping item {idx}: not an object"))
                skipped += 1
                continue

            if ok_only and item.get("status", "").strip().lower() != "ok":
                skipped += 1
                continue

            external_id = str(item.get("listing_no") or item.get("external_id") or "").strip()
            if not external_id:
                self.stdout.write(self.style.WARNING(f"Skipping item {idx}: missing listing ID"))
                skipped += 1
                continue

            title = str(item.get("title") or "").strip()
            price = parse_price(item.get("price"))
            ad_date = parse_date(item.get("listing_date"))
            deal_type = normalize_deal_type(item.get("real_estate"))
            property_type = str(item.get("real_estate_type") or "").strip()
            m2_gross = parse_int(item.get("gross_m2"))
            m2_net = parse_int(item.get("net_m2"))
            rooms_raw = str(item.get("rooms") or "").strip()
            bedrooms = rooms_raw
            rooms_text = rooms_raw
            building_age = parse_int(item.get("building_age"))
            floor_number = parse_int(item.get("floor_number"))
            floors_total = parse_int(item.get("number_of_floors"))
            heating = str(item.get("heating") or "").strip()
            description = str(item.get("description_text") or "").strip()
            latitude = None
            longitude = None
            try:
                latitude = float(str(item.get("lat") or "").strip()) if item.get("lat") not in (None, "") else None
            except ValueError:
                latitude = None
            try:
                longitude = float(str(item.get("lon") or "").strip()) if item.get("lon") not in (None, "") else None
            except ValueError:
                longitude = None

            raw_address = str(item.get("address") or "").strip()
            address, city, state = parse_address(raw_address)
            original_url = build_original_url(external_id)

            listing_values = {
                "realtor": realtor,
                "title": title,
                "address": address,
                "city": city,
                "state": state,
                "zipcode": "",
                "latitude": latitude,
                "longitude": longitude,
                "description": description,
                "price": price,
                "bedrooms": bedrooms,
                "deal_type": deal_type,
                "property_type": property_type,
                "bathrooms": 0,
                "garage": 0,
                "sqft": 0,
                "lot_size": 0.0,
                "external_id": external_id,
                "ad_date": ad_date,
                "original_url": original_url,
                "m2_gross": m2_gross,
                "m2_net": m2_net,
                "rooms_text": rooms_text,
                "building_age": building_age,
                "floor_number": floor_number,
                "floors_total": floors_total,
                "heating": heating,
                "kitchen_type": "",
                "balcony": "",
                "elevator": None,
                "parking_area": "",
                "furnished": None,
                "usage_status": "",
                "in_complex": None,
                "complex_name": "",
                "maintenance_fee": None,
                "deposit": None,
                "deed_status": "",
                "from_whom": "",
                "is_published": True,
            }
            if source_batch_label:
                listing_values["source_batch_label"] = source_batch_label
            if source_search_context:
                listing_values["source_search_context"] = source_search_context

            listing = Listing.objects.filter(external_id=external_id).first()
            if listing is not None:
                if update_existing:
                    for field_name, value in listing_values.items():
                        setattr(listing, field_name, value)
                    if ad_date:
                        listing.list_date = timezone.make_aware(
                            datetime.combine(ad_date, datetime.min.time()),
                            timezone.get_default_timezone(),
                        )
                    listing.save()
                    updated += 1
                    self.stdout.write(self.style.SUCCESS(f"Updated listing {external_id} (row {idx})"))
                else:
                    self.stdout.write(self.style.WARNING(f"Skipped existing listing {external_id} (row {idx})"))
                    skipped += 1
                continue

            listing = Listing(**listing_values)
            if ad_date:
                listing.list_date = timezone.make_aware(
                    datetime.combine(ad_date, datetime.min.time()),
                    timezone.get_default_timezone(),
                )
            if not dry_run:
                listing.save()
            created += 1
            self.stdout.write(self.style.SUCCESS(f"Created listing {external_id} (row {idx})"))

        if dry_run:
            transaction.set_rollback(True)

        self.stdout.write(self.style.SUCCESS(
            f"Finished JSON import: created={created} updated={updated} skipped={skipped}"
        ))
