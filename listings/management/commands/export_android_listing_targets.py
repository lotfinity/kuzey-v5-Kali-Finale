import json
from pathlib import Path

from django.core.management.base import BaseCommand

from listings.models import Listing, ListingPhoneEntry


class Command(BaseCommand):
    help = "Export observed Sahibinden external IDs that are not yet Listing rows."

    def add_arguments(self, parser):
        parser.add_argument("output_json", type=str, help="Where to write the target JSON")

    def handle(self, *args, **options):
        output_path = Path(options["output_json"])

        observed_ids = set(
            ListingPhoneEntry.objects.exclude(external_id="")
            .values_list("external_id", flat=True)
        )
        db_ids = set(
            Listing.objects.exclude(external_id="")
            .values_list("external_id", flat=True)
        )
        target_ids = sorted(observed_ids - db_ids)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(
                {
                    "target_listing_nos": target_ids,
                    "summary": {
                        "observed_index_unique": len(observed_ids),
                        "already_in_db": len(observed_ids & db_ids),
                        "missing_from_db": len(target_ids),
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
                "observed_index_unique=%s already_in_db=%s missing_from_db=%s output=%s"
                % (len(observed_ids), len(observed_ids & db_ids), len(target_ids), output_path)
            )
        )
