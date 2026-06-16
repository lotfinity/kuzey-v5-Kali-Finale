from django.core.management.base import BaseCommand

from listings.models import Listing, ListingPhoneEntry


class Command(BaseCommand):
    help = "Create ListingPhoneEntry audit rows for existing Listing.phone values."

    def add_arguments(self, parser):
        parser.add_argument(
            "--source",
            default="listing_phone_backfill",
            help="Source label for generated audit rows",
        )

    def handle(self, *args, **options):
        source = options["source"]
        created = 0
        updated = 0

        qs = Listing.objects.exclude(external_id="").exclude(phone="")
        for listing in qs:
            entry, was_created = ListingPhoneEntry.objects.get_or_create(
                external_id=listing.external_id,
                source=source,
                defaults={
                    "listing": listing,
                    "phone_normalized": listing.phone,
                    "phone_raw": listing.phone,
                    "status": ListingPhoneEntry.STATUS_OK,
                },
            )
            if was_created:
                created += 1
                continue
            changed = False
            if entry.listing_id != listing.pk:
                entry.listing = listing
                changed = True
            if entry.phone_normalized != listing.phone:
                entry.phone_normalized = listing.phone
                entry.phone_raw = listing.phone
                entry.status = ListingPhoneEntry.STATUS_OK
                changed = True
            if changed:
                entry.save()
                updated += 1

        self.stdout.write(
            self.style.SUCCESS(
                "processed=%s created=%s updated=%s"
                % (qs.count(), created, updated)
            )
        )
