import json

from django.core.management.base import BaseCommand, CommandError

from listings.models import Listing
from listings.portfolio import DEFAULT_MAX_COMP_RADIUS_KM, build_listing_portfolio_context


class Command(BaseCommand):
    help = "Rank or inspect reusable single-listing portfolio candidates."

    def add_arguments(self, parser):
        parser.add_argument(
            "--listing-id",
            action="append",
            type=int,
            default=[],
            help="Inspect a specific listing ID. Can be supplied multiple times.",
        )
        parser.add_argument("--top", type=int, default=10, help="Number of ranked candidates to print.")
        parser.add_argument("--scan-limit", type=int, default=250, help="Maximum published listings to scan.")
        parser.add_argument("--min-comp-count", type=int, default=3)
        parser.add_argument("--max-comp-radius-km", type=float, default=DEFAULT_MAX_COMP_RADIUS_KM)
        parser.add_argument(
            "--destination",
            default="",
            help="Optional Airbnb source_destination_query filter. Leave empty to use all local comps.",
        )
        parser.add_argument("--language", default="fr", help="Language prefix to show in portfolio URLs.")
        parser.add_argument("--json", action="store_true", help="Print ranked output as JSON.")

    def handle(self, *args, **options):
        listing_ids = options["listing_id"]
        destination = options["destination"] or None
        qs = Listing.objects.filter(is_published=True)
        if listing_ids:
            qs = qs.filter(id__in=listing_ids)
        else:
            qs = qs.order_by("-list_date", "id")[: options["scan_limit"]]

        rows = []
        skipped_missing_coords = 0
        for listing in qs:
            if listing.latitude is None or listing.longitude is None:
                skipped_missing_coords += 1
                continue
            context = build_listing_portfolio_context(
                listing,
                max_comp_radius_km=options["max_comp_radius_km"],
                destination=destination,
            )
            rentability = context["rentability"]
            price_summary = context["price_summary"]
            comp_count = price_summary.get("count") or 0
            if not listing_ids and comp_count < options["min_comp_count"]:
                continue
            rows.append({
                "id": listing.id,
                "title": listing.title,
                "price": int(listing.price or 0),
                "location": ", ".join(part for part in [listing.address, listing.state, listing.city] if part),
                "rooms": listing.rooms_text or listing.bedrooms,
                "portfolio_url": self.portfolio_url(listing.id, options["language"]),
                "airbnb_comp_count": comp_count,
                "airbnb_median_30_day": price_summary.get("median") or 0,
                "airbnb_p75_30_day": price_summary.get("p75") or 0,
                "estimated_net_monthly": rentability["airbnb_net"],
                "operator_net_monthly": rentability["operator_net"],
                "roi_percent": rentability["airbnb_roi"],
                "operator_roi_percent": rentability["operator_roi"],
                "payback_years": rentability["monthly_debt_free_payback_years"],
                "anchor_count": len(context["demand_anchors"]),
                "primary_anchor": context["primary_anchor"]["title"] if context["primary_anchor"] else "",
                "selected_airbnb_destination": context["selected_airbnb_destination"],
                "read": context["investment_read"],
            })

        rows = sorted(
            rows,
            key=lambda item: (
                item["roi_percent"],
                item["airbnb_comp_count"],
                item["anchor_count"],
                -item["price"],
            ),
            reverse=True,
        )

        if listing_ids and not rows:
            raise CommandError("No portfolio-ready listings found for the requested ID(s). Check coordinates and publication state.")

        if options["json"]:
            self.stdout.write(json.dumps({
                "count": len(rows),
                "skipped_missing_coords": skipped_missing_coords,
                "results": rows[: options["top"]],
            }, ensure_ascii=False, indent=2))
            return

        self.stdout.write(
            "Portfolio candidates: %s found, %s skipped for missing coordinates"
            % (len(rows), skipped_missing_coords)
        )
        for idx, item in enumerate(rows[: options["top"]], start=1):
            self.stdout.write(
                "%s. #%s %s | price ₺%s | Airbnb ₺%s/30d | net ₺%s/mo | ROI %.1f%% | comps %s | %s"
                % (
                    idx,
                    item["id"],
                    item["title"][:70],
                    item["price"],
                    item["airbnb_median_30_day"],
                    item["estimated_net_monthly"],
                    item["roi_percent"],
                    item["airbnb_comp_count"],
                    item["portfolio_url"],
                )
            )
            if item["primary_anchor"]:
                self.stdout.write("   anchor: %s" % item["primary_anchor"])
            if item["selected_airbnb_destination"]:
                self.stdout.write("   airbnb market: %s" % item["selected_airbnb_destination"])
            self.stdout.write("   read: %s" % item["read"])

    @staticmethod
    def portfolio_url(listing_id, language):
        return "/%s/listing/%s/portfolio/" % (language.strip("/") or "fr", listing_id)
