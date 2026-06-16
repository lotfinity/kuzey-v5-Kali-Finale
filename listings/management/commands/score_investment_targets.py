import json

from django.core.management.base import BaseCommand

from listings.investor import DEFAULT_INVESTOR_SETTINGS, build_investor_summary


class Command(BaseCommand):
    help = "Score sale listings for medical-tourism furnished-rental investment."

    def add_arguments(self, parser):
        parser.add_argument("--budget", type=int, default=DEFAULT_INVESTOR_SETTINGS["budget"])
        parser.add_argument("--reserve-percent", type=float, default=DEFAULT_INVESTOR_SETTINGS["reserve_percent"])
        parser.add_argument("--furnishing-per-unit", type=int, default=DEFAULT_INVESTOR_SETTINGS["furnishing_per_unit"])
        parser.add_argument("--legal-buffer-per-unit", type=int, default=DEFAULT_INVESTOR_SETTINGS["legal_buffer_per_unit"])
        parser.add_argument("--base-occupancy-percent", type=float, default=DEFAULT_INVESTOR_SETTINGS["base_occupancy_percent"])
        parser.add_argument("--operator-occupancy-uplift-percent", type=float, default=DEFAULT_INVESTOR_SETTINGS["operator_occupancy_uplift_percent"])
        parser.add_argument("--operator-revenue-uplift-percent", type=float, default=DEFAULT_INVESTOR_SETTINGS["operator_revenue_uplift_percent"])
        parser.add_argument("--private-network-confidence-percent", type=float, default=DEFAULT_INVESTOR_SETTINGS["private_network_confidence_percent"])
        parser.add_argument("--max-comp-radius-km", type=float, default=DEFAULT_INVESTOR_SETTINGS["max_comp_radius_km"])
        parser.add_argument("--limit", type=int, default=10)
        parser.add_argument("--json", action="store_true", help="Print the full summary as JSON")

    def handle(self, *args, **options):
        settings = dict(DEFAULT_INVESTOR_SETTINGS)
        for key in settings:
            if key in options:
                settings[key] = options[key]

        summary = build_investor_summary(settings)
        if options["json"]:
            self.stdout.write(json.dumps(summary, ensure_ascii=False, indent=2))
            return

        market = summary["market"]
        self.stdout.write(
            "Investor scoring: %s sale listings, %s Airbnb comps, budget ₺%s"
            % (market["sale_listing_count"], market["airbnb_comp_count"], settings["budget"])
        )
        self.stdout.write("")
        self.stdout.write("Top targets")
        for idx, item in enumerate(summary["ranked"][: options["limit"]], start=1):
            operator = item["scenarios"]["operator"]
            base = item["scenarios"]["base"]
            self.stdout.write(
                "%s. #%s %s | price ₺%s | op ROI %.2f%% | base net ₺%s/mo | comps %s | %s"
                % (
                    idx,
                    item["id"],
                    item["title"][:70],
                    item["price"],
                    operator["roi_percent"],
                    base["net_monthly"],
                    item["comp_count"],
                    item["shortlist"],
                )
            )
        self.stdout.write("")
        self.stdout.write("Top portfolios")
        for idx, item in enumerate(summary["portfolios"][:5], start=1):
            self.stdout.write(
                "%s. %s | deployed ₺%s | net ₺%s/mo | ROI %.2f%% | ids %s"
                % (idx, item["label"], item["deployed"], item["operator_net_monthly"], item["roi_percent"], ",".join(map(str, item["listing_ids"])))
            )
