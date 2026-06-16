from django.core.management import call_command
from django.core.management.base import BaseCommand

from listings.investor import MEDICAL_CORE_DISTRICTS
from listings.models import AirbnbListing


class Command(BaseCommand):
    help = "Fetch Airbnb comps across the medical-core Istanbul districts used by the investor dashboard."

    def add_arguments(self, parser):
        parser.add_argument("--district", action="append", dest="districts", help="District to fetch. Repeatable.")
        parser.add_argument("--pages", type=int, default=1)
        parser.add_argument("--call-budget", type=int, default=40)
        parser.add_argument("--arrival-date", default="2026-07-01")
        parser.add_argument("--departure-date", default="2026-07-31")
        parser.add_argument("--adult-guests", type=int, default=2)
        parser.add_argument("--currency-code", default="TRY")
        parser.add_argument("--replace-airbnb", action="store_true")

    def handle(self, *args, **options):
        districts = options["districts"] or MEDICAL_CORE_DISTRICTS
        if options["replace_airbnb"]:
            AirbnbListing.objects.all().delete()
            self.stdout.write(self.style.WARNING("Deleted existing Airbnb comps before market fetch."))

        calls = 0
        for district in districts:
            for page in range(1, options["pages"] + 1):
                if calls >= options["call_budget"]:
                    self.stdout.write(self.style.WARNING("Stopped at --call-budget=%s." % options["call_budget"]))
                    return
                destination = "%s, Istanbul, Turkey" % district
                self.stdout.write(self.style.NOTICE("Fetching %s page %s" % (destination, page)))
                call_command(
                    "fetch_airbnb_listings",
                    destination=destination,
                    arrival_date=options["arrival_date"],
                    departure_date=options["departure_date"],
                    adult_guests=options["adult_guests"],
                    page_number=page,
                    currency_code=options["currency_code"],
                    replace_airbnb=False,
                )
                calls += 1

        self.stdout.write(self.style.SUCCESS("Fetched %s Airbnb market pages." % calls))
