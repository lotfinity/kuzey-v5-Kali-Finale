import csv
from decimal import Decimal, InvalidOperation

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from listings.models import Listing
from realtors.models import Realtor


def to_int(value, field_name):
    if value is None or str(value).strip() == "":
        return None
    try:
        return int(str(value).strip())
    except ValueError:
        raise CommandError(f"Invalid integer for {field_name}: {value}")


def to_decimal(value, field_name):
    if value is None or str(value).strip() == "":
        return None
    try:
        return Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        raise CommandError(f"Invalid decimal for {field_name}: {value}")


def to_bool(value):
    if isinstance(value, bool):
        return value
    s = str(value).strip().lower()
    return s in {"1", "true", "yes", "y"}


class Command(BaseCommand):
    help = "Import listings from a CSV file. Headers must match the sample file."

    def add_arguments(self, parser):
        parser.add_argument("csv_path", type=str, help="Path to the CSV file")
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Validate and show summary without writing to the database",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        csv_path = options["csv_path"]
        dry_run = options["dry_run"]

        required_headers = [
            "realtor",
            "title",
            "address",
            "city",
            "state",
            "zipcode",
            "description",
            "price",
            "bedrooms",
            "property_type",
            "bathrooms",
            "garage",
            "sqft",
            "lot_size",
            "is_published",
        ]

        created = 0
        skipped = 0
        missing_realtor_rows = []

        try:
            with open(csv_path, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                headers = reader.fieldnames or []
                missing_headers = [h for h in required_headers if h not in headers]
                if missing_headers:
                    raise CommandError(
                        f"CSV is missing required headers: {', '.join(missing_headers)}"
                    )

                for idx, row in enumerate(reader, start=2):  # start=2 to account for header line
                    realtor_id = to_int(row.get("realtor"), "realtor")
                    if realtor_id is None:
                        self.stdout.write(self.style.WARNING(f"Row {idx}: missing realtor id, skipping"))
                        skipped += 1
                        continue

                    realtor = Realtor.objects.filter(id=realtor_id).first()
                    if not realtor:
                        missing_realtor_rows.append(idx)
                        skipped += 1
                        continue

                    listing = Listing(
                        realtor=realtor,
                        title=(row.get("title") or "").strip(),
                        address=(row.get("address") or "").strip(),
                        city=(row.get("city") or "").strip(),
                        state=(row.get("state") or "").strip(),
                        zipcode=(row.get("zipcode") or "").strip(),
                        description=(row.get("description") or "").strip(),
                        price=to_int(row.get("price"), "price") or 0,
                        bedrooms=str(row.get("bedrooms") or "").strip() or "",
                        property_type=(row.get("property_type") or "").strip(),
                        bathrooms=to_int(row.get("bathrooms"), "bathrooms") or 0,
                        garage=to_int(row.get("garage"), "garage") or 0,
                        sqft=to_int(row.get("sqft"), "sqft") or 0,
                        lot_size=to_decimal(row.get("lot_size"), "lot_size") or Decimal("0.0"),
                        is_published=to_bool(row.get("is_published")),
                    )

                    if dry_run:
                        # Validate by attempting to clean fields where applicable
                        pass
                    else:
                        listing.save()
                        created += 1

        except FileNotFoundError:
            raise CommandError(f"CSV file not found: {csv_path}")

        if dry_run:
            transaction.set_rollback(True)

        if missing_realtor_rows:
            self.stdout.write(
                self.style.WARNING(
                    f"Skipped rows due to missing Realtor IDs: {missing_realtor_rows}"
                )
            )

        self.stdout.write(self.style.SUCCESS(f"Created {created} listings. Skipped {skipped} rows."))

