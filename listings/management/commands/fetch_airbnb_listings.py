from decimal import Decimal, InvalidOperation

import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from listings.models import AirbnbListing, CurrencySettings


def as_decimal(value):
    if value in (None, ''):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def as_int(value):
    if value in (None, ''):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def convert_money(value, from_currency, to_currency, rates):
    amount = as_decimal(value)
    if amount is None or from_currency == to_currency:
        return amount
    if from_currency == 'USD' and to_currency == 'TRY' and rates.try_to_usd:
        return amount / rates.try_to_usd
    if from_currency == 'EUR' and to_currency == 'TRY' and rates.try_to_eur:
        return amount / rates.try_to_eur
    return amount


def converted_pricing(pricing, target_currency, rates):
    source_currency = pricing.get('currency') or 'USD'
    converted = dict(pricing)
    converted['currency'] = target_currency
    converted['nightly_rate'] = float(convert_money(pricing.get('nightly_rate'), source_currency, target_currency, rates) or 0)
    converted['total_cost'] = float(convert_money(pricing.get('total_cost'), source_currency, target_currency, rates) or 0)
    converted['source_currency'] = source_currency
    converted['source_pricing'] = pricing
    breakdown = []
    for item in pricing.get('cost_breakdown') or []:
        copied = dict(item)
        copied['amount'] = float(convert_money(copied.get('amount'), source_currency, target_currency, rates) or 0)
        breakdown.append(copied)
    converted['cost_breakdown'] = breakdown
    return converted


class Command(BaseCommand):
    help = 'Fetch Airbnb listings from Omkar Cloud and upsert them into AirbnbListing.'

    def add_arguments(self, parser):
        parser.add_argument('--api-key', default=getattr(settings, 'AIRBNB_SCRAPER_API_KEY', ''))
        parser.add_argument('--destination', default='Esenyurt, Istanbul, Turkey')
        parser.add_argument('--arrival-date', default='2026-07-01')
        parser.add_argument('--departure-date', default='2026-07-31')
        parser.add_argument('--adult-guests', type=int, default=2)
        parser.add_argument('--page-number', type=int, default=1)
        parser.add_argument('--currency-code', default='TRY')
        parser.add_argument('--replace-airbnb', action='store_true')

    def handle(self, *args, **options):
        api_key = options['api_key']
        if not api_key:
            raise CommandError('Provide --api-key or AIRBNB_SCRAPER_API_KEY in settings/env.')

        params = {
            'destination_query': options['destination'],
            'arrival_date': options['arrival_date'],
            'departure_date': options['departure_date'],
            'adult_guests': options['adult_guests'],
            'page_number': options['page_number'],
        }
        response = requests.get(
            'https://airbnb-scraper-api.omkar.cloud/airbnb/listings/search',
            params=params,
            headers={'API-Key': api_key, 'Accept': 'application/json'},
            timeout=90,
        )
        response.raise_for_status()
        payload = response.json()
        listings = payload.get('listings') or []
        now = timezone.now()
        rates = CurrencySettings.load()
        target_currency = options['currency_code']
        if options['replace_airbnb']:
            AirbnbListing.objects.all().delete()
        created = 0
        updated = 0

        for item in listings:
            listing_id = str(item.get('listing_id') or '').strip()
            if not listing_id:
                continue
            pricing = item.get('pricing') or {}
            source_currency = pricing.get('currency') or 'USD'
            display_pricing = converted_pricing(pricing, target_currency, rates)
            defaults = {
                'title': item.get('title') or '',
                'property_type': item.get('property_type') or '',
                'listing_url': item.get('listing_url') or '',
                'booking_url': item.get('booking_url') or '',
                'city': item.get('city') or '',
                'full_address': item.get('full_address') or '',
                'latitude': item.get('latitude'),
                'longitude': item.get('longitude'),
                'bedroom_count': as_int(item.get('bedroom_count')),
                'bathroom_count': as_decimal(item.get('bathroom_count')),
                'bed_count': as_int(item.get('bed_count')),
                'guest_capacity': as_int(item.get('guest_capacity')),
                'photos': item.get('photos') or [],
                'amenity_ids': item.get('amenity_ids') or [],
                'host_id': str(item.get('host_id') or ''),
                'host_avatar': item.get('host_avatar') or '',
                'is_superhost': bool(item.get('is_superhost')),
                'overall_rating': as_decimal(item.get('overall_rating')),
                'review_count': as_int(item.get('review_count')),
                'nightly_rate': convert_money(pricing.get('nightly_rate'), source_currency, target_currency, rates),
                'currency': target_currency,
                'total_cost': convert_money(pricing.get('total_cost'), source_currency, target_currency, rates),
                'pricing': display_pricing,
                'cancellation_policy': item.get('cancellation_policy') or '',
                'is_rare_find': bool(item.get('is_rare_find')),
                'rank': as_int(item.get('rank')),
                'source_destination_query': options['destination'],
                'search_adult_guests': options['adult_guests'],
                'search_page_number': options['page_number'],
                'raw_search_payload': item,
                'scraped_at': now,
            }
            _, was_created = AirbnbListing.objects.update_or_create(
                listing_id=listing_id,
                defaults=defaults,
            )
            if was_created:
                created += 1
            else:
                updated += 1

        self.stdout.write(self.style.SUCCESS(
            'Fetched %s total_results; upserted %s listings (%s created, %s updated).'
            % (payload.get('total_results'), len(listings), created, updated)
        ))
