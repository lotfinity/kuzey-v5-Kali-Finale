from datetime import timedelta

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.utils import timezone

from listings.investor import MEDICAL_CORE_DISTRICTS
from listings.models import AirbnbListing


DEFAULT_HEATMAP_DESTINATIONS = [
    "Gokevler, Esenyurt, Istanbul, Turkey",
    "Gökevler, Esenyurt, Istanbul, Turkey",
    "TUYAP, Beylikdüzü, Istanbul, Turkey",
    "Cumhuriyet Mahallesi, Beylikdüzü, Istanbul, Turkey",
    "İncirtepe, Esenyurt, Istanbul, Turkey",
    "Haramidere, Esenyurt, Istanbul, Turkey",
]


class Command(BaseCommand):
    help = "Refresh cached Airbnb data for MapLibre revenue heatmap markets."

    def add_arguments(self, parser):
        parser.add_argument(
            "--destination",
            action="append",
            default=[],
            help="Destination query to fetch. Repeatable. Defaults to heatmap micro-areas plus medical-core districts.",
        )
        parser.add_argument("--pages", type=int, default=1)
        parser.add_argument("--call-budget", type=int, default=40)
        parser.add_argument("--arrival-date", default="")
        parser.add_argument("--departure-date", default="")
        parser.add_argument("--adult-guests", type=int, default=2)
        parser.add_argument("--currency-code", default="TRY")
        parser.add_argument("--api-key", default="")
        parser.add_argument("--small-flats-only", action="store_true", help="Kept for workflow clarity; API filtering happens after caching.")
        parser.add_argument("--replace-airbnb", action="store_true")

    def handle(self, *args, **options):
        arrival_date = options["arrival_date"] or (timezone.localdate() + timedelta(days=1)).isoformat()
        departure_date = options["departure_date"] or (timezone.localdate() + timedelta(days=31)).isoformat()

        destinations = options["destination"] or self.default_destinations()
        destinations = list(dict.fromkeys([item.strip() for item in destinations if item and item.strip()]))

        if options["replace_airbnb"]:
            AirbnbListing.objects.all().delete()
            self.stdout.write(self.style.WARNING("Deleted existing Airbnb comps before heatmap refresh."))

        calls = 0
        for destination in destinations:
            for page in range(1, options["pages"] + 1):
                if calls >= options["call_budget"]:
                    self.stdout.write(self.style.WARNING("Stopped at --call-budget=%s." % options["call_budget"]))
                    return
                self.stdout.write(self.style.NOTICE(
                    "Fetching %s page %s for %s to %s"
                    % (destination, page, arrival_date, departure_date)
                ))
                fetch_options = {
                    "destination": destination,
                    "arrival_date": arrival_date,
                    "departure_date": departure_date,
                    "adult_guests": options["adult_guests"],
                    "page_number": page,
                    "currency_code": options["currency_code"],
                    "replace_airbnb": False,
                }
                if options["api_key"]:
                    fetch_options["api_key"] = options["api_key"]
                call_command("fetch_airbnb_listings", **fetch_options)
                calls += 1

        self.stdout.write(self.style.SUCCESS(
            "Fetched %s Airbnb heatmap market pages across %s destinations."
            % (calls, len(destinations))
        ))

    @staticmethod
    def default_destinations():
        district_destinations = ["%s, Istanbul, Turkey" % district for district in MEDICAL_CORE_DISTRICTS]
        return DEFAULT_HEATMAP_DESTINATIONS + district_destinations
