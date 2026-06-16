from django.core.management.base import BaseCommand
from django.db import transaction

from listings.models import Listing, ListingPhoneEntry


class Command(BaseCommand):
    help = "Link ListingPhoneEntry rows to Listing rows by external_id and backfill Listing.phone."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would change without writing to the database",
        )
        parser.add_argument(
            "--overwrite-phone",
            action="store_true",
            help="Overwrite Listing.phone when it already has a value",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        overwrite_phone = options["overwrite_phone"]

        linked = 0
        phones_backfilled = 0
        no_listing = 0

        entries = ListingPhoneEntry.objects.exclude(external_id="").order_by("external_id", "-scraped_at")
        for entry in entries:
            listing = Listing.objects.filter(external_id=entry.external_id).first()
            if not listing:
                no_listing += 1
                continue

            entry_changed = False
            if entry.listing_id != listing.pk:
                entry.listing = listing
                entry_changed = True
                linked += 1

            listing_changed = False
            if entry.phone_normalized and (overwrite_phone or not listing.phone):
                if listing.phone != entry.phone_normalized:
                    listing.phone = entry.phone_normalized
                    listing_changed = True
                    phones_backfilled += 1

            if not dry_run:
                if entry_changed:
                    entry.save(update_fields=["listing", "updated_at"])
                if listing_changed:
                    listing.save(update_fields=["phone"], skip_geocode=True)

        if dry_run:
            transaction.set_rollback(True)

        self.stdout.write(
            self.style.SUCCESS(
                "linked=%s phones_backfilled=%s no_listing=%s"
                % (linked, phones_backfilled, no_listing)
            )
        )
