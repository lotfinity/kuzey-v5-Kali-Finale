import json
import re
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q

from listings.models import Listing, ListingPhoneEntry


def normalize_phone(value):
    digits = re.sub(r"\D+", "", str(value or ""))
    if digits.startswith("90") and len(digits) == 12:
        digits = "0" + digits[2:]
    elif len(digits) == 10 and digits.startswith("5"):
        digits = "0" + digits
    if re.fullmatch(r"05\d{9}", digits):
        return digits
    return ""


class Command(BaseCommand):
    help = "Export Listing.external_id values that still need Android phone extraction."

    def add_arguments(self, parser):
        parser.add_argument("output_json", type=str, help="Where to write the target JSON")
        parser.add_argument(
            "--scraped-results",
            action="append",
            default=[],
            help="Existing Android results.json to treat as already available phone data",
        )

    def handle(self, *args, **options):
        output_path = Path(options["output_json"])
        known_phone_ids = set(
            ListingPhoneEntry.objects.exclude(phone_normalized="")
            .values_list("external_id", flat=True)
        )

        for scraped_path in options["scraped_results"]:
            path = Path(scraped_path)
            if not path.exists():
                raise CommandError(f"Scraped results JSON not found: {path}")
            try:
                rows = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise CommandError(f"Invalid JSON in {path}: {exc}") from exc
            if not isinstance(rows, list):
                raise CommandError(f"Expected a list in {path}")
            for row in rows:
                if not isinstance(row, dict):
                    continue
                external_id = str(row.get("listing_no") or "").strip()
                phone = normalize_phone(row.get("phone_normalized") or row.get("phone_raw"))
                if external_id and phone:
                    known_phone_ids.add(external_id)

        missing_qs = (
            Listing.objects.filter(Q(phone="") | Q(phone__isnull=True))
            .exclude(external_id="")
            .order_by("id")
        )
        targets = []
        excluded_with_known_phone = 0
        for listing in missing_qs:
            if listing.external_id in known_phone_ids:
                excluded_with_known_phone += 1
                continue
            targets.append(
                {
                    "listing_id": listing.pk,
                    "listing_no": listing.external_id,
                    "title": listing.title,
                    "price": listing.price,
                }
            )

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(
                {
                    "target_listing_nos": [item["listing_no"] for item in targets],
                    "targets": targets,
                    "summary": {
                        "db_missing_phone": missing_qs.count(),
                        "excluded_with_known_phone": excluded_with_known_phone,
                        "remaining_targets": len(targets),
                    },
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        self.stdout.write(
            self.style.SUCCESS(
                "db_missing_phone=%s excluded_with_known_phone=%s remaining_targets=%s output=%s"
                % (missing_qs.count(), excluded_with_known_phone, len(targets), output_path)
            )
        )
