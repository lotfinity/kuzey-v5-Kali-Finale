import json
import re
from datetime import datetime
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from listings.models import Listing, ListingPhoneEntry


def clean_int(value):
    if value in (None, ""):
        return None
    digits = re.findall(r"\d+", str(value))
    if not digits:
        return None
    return int("".join(digits))


def normalize_phone(value):
    digits = re.sub(r"\D+", "", str(value or ""))
    if digits.startswith("90") and len(digits) == 12:
        digits = "0" + digits[2:]
    elif len(digits) == 10 and digits.startswith("5"):
        digits = "0" + digits
    if re.fullmatch(r"05\d{9}", digits):
        return digits
    return ""


def parse_date(value):
    value = str(value or "").strip()
    if not value:
        return None
    for fmt in ("%d.%m.%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    return None


def parse_float(value):
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class Command(BaseCommand):
    help = "Import Sahibinden Android pipeline results into existing listings by external_id."

    def add_arguments(self, parser):
        parser.add_argument("results_json", type=str, help="Path to Android pipeline results.json")
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would change without writing to the database",
        )
        parser.add_argument(
            "--include-errors",
            action="store_true",
            help="Import usable fields from rows marked as error",
        )
        parser.add_argument(
            "--overwrite-phone",
            action="store_true",
            help="Overwrite Listing.phone when it already has a value",
        )
        parser.add_argument(
            "--details",
            action="store_true",
            help="Also update coordinates and parsed listing detail fields",
        )
        parser.add_argument(
            "--source",
            default="android_visible_index",
            help="Source name stored on ListingPhoneEntry rows",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        path = Path(options["results_json"])
        if not path.exists():
            raise CommandError(f"JSON file not found: {path}")

        try:
            rows = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise CommandError(f"Invalid JSON in {path}: {exc}") from exc

        if not isinstance(rows, list):
            raise CommandError("Expected results JSON to be a list of rows.")

        dry_run = options["dry_run"]
        include_errors = options["include_errors"]
        overwrite_phone = options["overwrite_phone"]
        update_details = options["details"]
        source = options["source"]

        matched = 0
        updated = 0
        phone_entries_upserted = 0
        skipped_error = 0
        skipped_no_external_id = 0
        skipped_no_match = 0
        skipped_no_changes = 0

        for row in rows:
            if not isinstance(row, dict):
                continue

            external_id = str(row.get("listing_no") or "").strip()
            if not external_id:
                skipped_no_external_id += 1
                continue

            listing = Listing.objects.filter(external_id=external_id).first()
            phone = normalize_phone(row.get("phone_normalized") or row.get("phone_raw"))
            row_status = str(row.get("status") or "").strip() or ListingPhoneEntry.STATUS_MISSING
            if row_status not in dict(ListingPhoneEntry.STATUS_CHOICES):
                row_status = ListingPhoneEntry.STATUS_ERROR if row.get("error") else ListingPhoneEntry.STATUS_MISSING
            if phone:
                row_status = ListingPhoneEntry.STATUS_OK

            if not dry_run:
                entry, _ = ListingPhoneEntry.objects.get_or_create(
                    external_id=external_id,
                    source=source,
                )
                entry.listing = listing
                if phone or not entry.phone_normalized:
                    entry.phone_normalized = phone
                    entry.phone_raw = str(row.get("phone_raw") or "")
                    entry.status = row_status
                elif row_status == ListingPhoneEntry.STATUS_OK:
                    entry.status = row_status
                entry.source_result_path = str(path)
                entry.debug_folder = str(row.get("debug_folder") or "")
                entry.error = str(row.get("error") or "")
                entry.save()
            phone_entries_upserted += 1

            if row.get("status") == "error" and not include_errors:
                skipped_error += 1
                continue

            if not listing:
                skipped_no_match += 1
                continue

            matched += 1
            changed_fields = []
            if phone and (overwrite_phone or not listing.phone):
                if listing.phone != phone:
                    listing.phone = phone
                    changed_fields.append("phone")

            if update_details:
                lat = parse_float(row.get("lat"))
                lon = parse_float(row.get("lon"))
                if lat is not None and listing.latitude != lat:
                    listing.latitude = lat
                    changed_fields.append("latitude")
                if lon is not None and listing.longitude != lon:
                    listing.longitude = lon
                    changed_fields.append("longitude")

                field_map = {
                    "title": row.get("title"),
                    "address": row.get("address"),
                    "price": clean_int(row.get("price")),
                    "m2_gross": clean_int(row.get("gross_m2")),
                    "m2_net": clean_int(row.get("net_m2")),
                    "rooms_text": row.get("rooms"),
                    "building_age": clean_int(row.get("building_age")),
                    "floor_number": clean_int(row.get("floor_number")),
                    "floors_total": clean_int(row.get("number_of_floors")),
                    "heating": row.get("heating"),
                    "ad_date": parse_date(row.get("listing_date")),
                }
                real_estate_type = str(row.get("real_estate_type") or "").strip()
                if real_estate_type:
                    field_map["property_type"] = real_estate_type
                if field_map.get("m2_gross"):
                    field_map["sqft"] = int(round(field_map["m2_gross"] * 10.7639))

                for field, value in field_map.items():
                    if value in (None, ""):
                        continue
                    if getattr(listing, field) != value:
                        setattr(listing, field, value)
                        changed_fields.append(field)

            if not changed_fields:
                skipped_no_changes += 1
                continue

            if not dry_run:
                listing.save(update_fields=sorted(set(changed_fields)), skip_geocode=True)
            updated += 1
            self.stdout.write(
                "%s listing id=%s external_id=%s fields=%s"
                % (
                    "Would update" if dry_run else "Updated",
                    listing.pk,
                    external_id,
                    ",".join(sorted(set(changed_fields))),
                )
            )

        if dry_run:
            transaction.set_rollback(True)

        self.stdout.write(
            self.style.SUCCESS(
                "Rows=%s matched=%s updated=%s skipped_error=%s skipped_no_external_id=%s "
                "skipped_no_match=%s skipped_no_changes=%s phone_entries_upserted=%s"
                % (
                    len(rows),
                    matched,
                    updated,
                    skipped_error,
                    skipped_no_external_id,
                    skipped_no_match,
                    skipped_no_changes,
                    phone_entries_upserted,
                )
            )
        )
