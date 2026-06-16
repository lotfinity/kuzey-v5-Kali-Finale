import json
from pathlib import Path

from django.core.management.base import BaseCommand

from listings.models import Listing


def format_price(value):
    try:
        number = int(value)
    except (TypeError, ValueError):
        return ""
    return f"{number:,}".replace(",", ".") + " TL"


class Command(BaseCommand):
    help = "Export listings without images as Android gallery capture targets."

    def add_arguments(self, parser):
        parser.add_argument("output_json", type=str, help="Where to write target JSON")

    def handle(self, *args, **options):
        output_path = Path(options["output_json"])
        qs = (
            Listing.objects.filter(images__isnull=True)
            .exclude(external_id="")
            .order_by("id")
        )
        rows = []
        for listing in qs:
            price = format_price(listing.price)
            rows.append(
                {
                    "listing_no": listing.external_id,
                    "external_id": listing.external_id,
                    "title": listing.title,
                    "price": price,
                    "source_index_title": listing.title,
                    "source_index_price": price,
                    "db_id": listing.pk,
                }
            )

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        self.stdout.write(
            self.style.SUCCESS(
                "image_targets=%s output=%s" % (len(rows), output_path)
            )
        )
