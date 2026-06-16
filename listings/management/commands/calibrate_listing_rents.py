import math
import re
from statistics import median

from django.core.management.base import BaseCommand
from django.utils import timezone

from listings.models import AirbnbListing, Listing


def valid_coord(lat, lng):
    try:
        latf = float(lat)
        lngf = float(lng)
    except (TypeError, ValueError):
        return False
    return -90.0 <= latf <= 90.0 and -180.0 <= lngf <= 180.0 and not (latf == 0.0 and lngf == 0.0)


def distance_km(lat1, lng1, lat2, lng2):
    radius = 6371.0088
    phi1 = math.radians(float(lat1))
    phi2 = math.radians(float(lat2))
    d_phi = math.radians(float(lat2) - float(lat1))
    d_lam = math.radians(float(lng2) - float(lng1))
    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lam / 2) ** 2
    )
    return radius * (2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)))


def listing_room_size(listing):
    raw = str(listing.rooms_text or listing.bedrooms or '').lower().replace(' ', '')
    match = re.search(r'\d+\+\d+', raw)
    return match.group(0) if match else ''


def airbnb_room_size(airbnb):
    bedrooms = airbnb.bedroom_count or 0
    if bedrooms <= 0:
        return '1+0'
    return '%s+1' % bedrooms


def monthly_airbnb_price(airbnb, stay_days):
    if airbnb.total_cost is not None:
        return float(airbnb.total_cost)
    if airbnb.nightly_rate is not None:
        return float(airbnb.nightly_rate) * stay_days
    return None


def round_to_step(value, step):
    if not step:
        return int(round(value))
    return int(round(float(value) / step) * step)


class Command(BaseCommand):
    help = 'Calibrate sale listing monthly rent estimates from nearby real Airbnb prices.'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true', help='Persist calibrated estimates.')
        parser.add_argument('--factor', type=float, default=1.0, help='Multiplier applied to Airbnb median.')
        parser.add_argument('--stay-days', type=int, default=30, help='Days used when only nightly Airbnb rate exists.')
        parser.add_argument('--min-comps', type=int, default=3, help='Preferred minimum Airbnb comps per listing.')
        parser.add_argument('--radii-km', default='1.5,3,5', help='Comma-separated search radii in km.')
        parser.add_argument('--round-to', type=int, default=100, help='Round estimates to this TRY step.')
        parser.add_argument('--currency', default='TRY', help='Airbnb currency to use for comparison.')
        parser.add_argument('--limit', type=int, default=0, help='Limit number of sale listings processed.')
        parser.add_argument('--listing-id', type=int, action='append', help='Calibrate only selected listing id(s).')
        parser.add_argument(
            '--allow-room-fallback',
            action='store_true',
            help='Fallback to nearby Airbnb comps with any room size when room-matched comps are insufficient.',
        )

    def handle(self, *args, **options):
        radii = []
        for chunk in str(options['radii_km']).split(','):
            try:
                radius = float(chunk.strip())
            except ValueError:
                continue
            if radius > 0:
                radii.append(radius)
        if not radii:
            radii = [1.5, 3.0, 5.0]

        airbnbs = []
        for obj in AirbnbListing.objects.exclude(latitude__isnull=True).exclude(longitude__isnull=True):
            if not valid_coord(obj.latitude, obj.longitude):
                continue
            if options['currency'] and (obj.currency or '').upper() != options['currency'].upper():
                continue
            price = monthly_airbnb_price(obj, options['stay_days'])
            if price is None or price <= 0:
                continue
            airbnbs.append({
                'obj': obj,
                'lat': float(obj.latitude),
                'lng': float(obj.longitude),
                'room_size': airbnb_room_size(obj),
                'monthly_price': price,
            })

        qs = Listing.objects.filter(is_published=True).exclude(latitude__isnull=True).exclude(longitude__isnull=True).order_by('id')
        if options['listing_id']:
            qs = qs.filter(id__in=options['listing_id'])
        if options['limit']:
            qs = qs[:options['limit']]

        applied = 0
        eligible = 0
        skipped = 0
        now = timezone.now()

        self.stdout.write(
            'Mode: %s | Airbnb comps loaded: %s | factor: %.3f | radii: %s km'
            % ('APPLY' if options['apply'] else 'DRY RUN', len(airbnbs), options['factor'], ', '.join(str(r) for r in radii))
        )

        for listing in qs:
            if not valid_coord(listing.latitude, listing.longitude):
                skipped += 1
                continue

            room_size = listing_room_size(listing)
            selected = []
            selected_radius = None
            fallback_used = False

            for radius in radii:
                nearby = []
                for comp in airbnbs:
                    if room_size and comp['room_size'] != room_size:
                        continue
                    dist = distance_km(listing.latitude, listing.longitude, comp['lat'], comp['lng'])
                    if dist <= radius:
                        nearby.append((dist, comp))
                if len(nearby) >= options['min_comps'] or (nearby and radius == radii[-1]):
                    selected = nearby
                    selected_radius = radius
                    break

            if not selected and options['allow_room_fallback']:
                for radius in radii:
                    nearby = []
                    for comp in airbnbs:
                        dist = distance_km(listing.latitude, listing.longitude, comp['lat'], comp['lng'])
                        if dist <= radius:
                            nearby.append((dist, comp))
                    if len(nearby) >= options['min_comps'] or (nearby and radius == radii[-1]):
                        selected = nearby
                        selected_radius = radius
                        fallback_used = True
                        break

            if not selected:
                skipped += 1
                self.stdout.write(
                    'SKIP id=%s room=%s old=%s reason=no Airbnb comps'
                    % (listing.id, room_size or '-', listing.estimated_rent)
                )
                continue

            selected.sort(key=lambda item: item[0])
            comp_prices = [item[1]['monthly_price'] for item in selected]
            comp_median = round_to_step(median(comp_prices), options['round_to'])
            estimate = round_to_step(comp_median * options['factor'], options['round_to'])
            eligible += 1

            self.stdout.write(
                'id=%s room=%s old=%s median=%s new=%s comps=%s radius=%.1fkm%s'
                % (
                    listing.id,
                    room_size or '-',
                    listing.estimated_rent,
                    comp_median,
                    estimate,
                    len(selected),
                    selected_radius or 0,
                    ' fallback-any-room' if fallback_used else '',
                )
            )

            if options['apply']:
                listing.estimated_monthly_rent_try = estimate
                listing.airbnb_comp_median_try = comp_median
                listing.airbnb_comp_count = len(selected)
                listing.rent_estimate_source = 'airbnb_nearby_median'
                listing.rent_estimate_updated_at = now
                listing.save(
                    update_fields=[
                        'estimated_monthly_rent_try',
                        'airbnb_comp_median_try',
                        'airbnb_comp_count',
                        'rent_estimate_source',
                        'rent_estimate_updated_at',
                    ],
                    skip_geocode=True,
                )
                applied += 1

        self.stdout.write(
            self.style.SUCCESS(
                'Done. eligible=%s applied=%s skipped=%s'
                % (eligible, applied, skipped)
            )
        )
