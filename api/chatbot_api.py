"""
Chatbot-Friendly API Endpoints for Listings

These endpoints are designed for AI chatbots to query listing data
and provide customer service based on available properties.

All endpoints are read-only (GET) and support extensive filtering.
"""

from __future__ import annotations

import json
from typing import Dict, List, Any, Optional
from decimal import Decimal

from django.http import JsonResponse, HttpRequest
from django.views.decorators.http import require_GET
from django.db.models import Q, Min, Max, Avg, Count
from django.conf import settings

from listings.models import Listing, ListingImage


def _get_base_url(request: HttpRequest) -> str:
    """Get the base URL for building absolute image URLs."""
    return request.build_absolute_uri('/').rstrip('/')


def _build_image_url(request: HttpRequest, image_path: str) -> str:
    """Build absolute URL for an image."""
    if not image_path:
        return ''
    base = _get_base_url(request)
    media_url = settings.MEDIA_URL.strip('/')
    return f"{base}/{media_url}/{image_path}"


def _listing_to_full_dict(request: HttpRequest, listing: Listing, include_images: bool = True) -> Dict[str, Any]:
    """Convert a Listing object to a comprehensive dictionary for AI consumption."""
    
    # Build the listing detail URL
    try:
        from django.urls import reverse
        detail_url = request.build_absolute_uri(reverse('new_listing_detail', args=[listing.id]))
    except Exception:
        detail_url = f"{_get_base_url(request)}/property/{listing.id}/"
    
    data = {
        'id': listing.id,
        'title': listing.title,
        'description': listing.description,
        
        # Location
        'location': {
            'address': listing.address,
            'city': listing.city,
            'state': listing.state,
            'zipcode': listing.zipcode,
            'latitude': listing.latitude,
            'longitude': listing.longitude,
            'google_maps_url': f"https://www.google.com/maps?q={listing.latitude},{listing.longitude}" if listing.latitude and listing.longitude else None,
        },
        
        # Pricing
        'pricing': {
            'price': listing.price,
            'price_formatted': f"{listing.price:,} TL",
            'deal_type': listing.deal_type,
            'deal_type_display': 'Kiralık' if listing.deal_type == 'kiralik' else 'Satılık',
            'deposit': listing.deposit,
            'maintenance_fee': listing.maintenance_fee,
        },
        
        # Property Details
        'property': {
            'type': listing.property_type,
            'bedrooms': listing.bedrooms,
            'bathrooms': listing.bathrooms,
            'rooms_text': listing.rooms_text,  # e.g., "2+1", "3+1"
            'sqft': listing.sqft,
            'm2_gross': listing.m2_gross,
            'm2_net': listing.m2_net,
            'lot_size': float(listing.lot_size) if listing.lot_size else None,
        },
        
        # Building Info
        'building': {
            'age': listing.building_age,
            'floor_number': listing.floor_number,
            'floors_total': listing.floors_total,
            'elevator': listing.elevator,
            'in_complex': listing.in_complex,
            'complex_name': listing.complex_name,
        },
        
        # Amenities & Features
        'amenities': {
            'heating': listing.heating,
            'kitchen_type': listing.kitchen_type,
            'balcony': listing.balcony,
            'parking_area': listing.parking_area,
            'furnished': listing.furnished,
            'garage': listing.garage,
        },
        
        # Status
        'status': {
            'usage_status': listing.usage_status,
            'deed_status': listing.deed_status,
            'from_whom': listing.from_whom,
            'is_published': listing.is_published,
            'list_date': listing.list_date.isoformat() if listing.list_date else None,
            'ad_date': listing.ad_date.isoformat() if listing.ad_date else None,
        },
        
        # Links
        'links': {
            'detail_page': detail_url,
            'original_source': listing.original_url,
        },
        
        # External Reference
        'external_id': listing.external_id,
    }
    
    # Add images if requested
    if include_images:
        images = listing.images.filter(is_visible=True).order_by('order', 'id')
        data['images'] = {
            'count': images.count(),
            'primary': None,
            'gallery': [],
        }
        
        for img in images:
            img_data = {
                'id': img.id,
                'url': _build_image_url(request, str(img.image)) if img.image else None,
                'title': img.title,
                'is_primary': img.is_primary,
            }
            data['images']['gallery'].append(img_data)
            if img.is_primary:
                data['images']['primary'] = img_data
        
        # If no primary set, use first image
        if not data['images']['primary'] and data['images']['gallery']:
            data['images']['primary'] = data['images']['gallery'][0]
    
    return data


def _listing_to_summary_dict(request: HttpRequest, listing: Listing) -> Dict[str, Any]:
    """Convert a Listing to a compact summary for list views."""
    
    # Get primary image
    primary_img = listing.images.filter(is_visible=True, is_primary=True).first()
    if not primary_img:
        primary_img = listing.images.filter(is_visible=True).first()
    
    try:
        from django.urls import reverse
        detail_url = request.build_absolute_uri(reverse('new_listing_detail', args=[listing.id]))
    except Exception:
        detail_url = f"{_get_base_url(request)}/property/{listing.id}/"
    
    return {
        'id': listing.id,
        'title': listing.title,
        'city': listing.city,
        'state': listing.state,
        'price': listing.price,
        'price_formatted': f"{listing.price:,} TL",
        'deal_type': listing.deal_type,
        'deal_type_display': 'Kiralık' if listing.deal_type == 'kiralik' else 'Satılık',
        'property_type': listing.property_type,
        'bedrooms': listing.bedrooms,
        'bathrooms': listing.bathrooms,
        'rooms_text': listing.rooms_text,
        'm2_net': listing.m2_net,
        'sqft': listing.sqft,
        'furnished': listing.furnished,
        'latitude': listing.latitude,
        'longitude': listing.longitude,
        'primary_image': _build_image_url(request, str(primary_img.image)) if primary_img and primary_img.image else None,
        'image_count': listing.images.filter(is_visible=True).count(),
        'detail_url': detail_url,
    }


@require_GET
def chatbot_listings_search(request: HttpRequest) -> JsonResponse:
    """
    Search and filter listings for AI chatbot consumption.
    
    Query Parameters:
    -----------------
    Filtering:
    - deal_type: 'kiralik' (rent) or 'satis' (sale)
    - property_type: Type of property (e.g., 'Daire', 'Villa')
    - city: City name (partial match)
    - state: State/district name (partial match)
    - min_price, max_price: Price range
    - min_bedrooms, max_bedrooms: Bedroom count range
    - min_bathrooms, max_bathrooms: Bathroom count range
    - min_sqft, max_sqft: Square footage range
    - min_m2, max_m2: Square meter range (m2_net)
    - rooms: Room configuration (e.g., '2+1', '3+1')
    - furnished: 'true' or 'false'
    - elevator: 'true' or 'false'
    - parking: 'true' if must have parking
    - in_complex: 'true' or 'false'
    - max_building_age: Maximum building age in years
    - floor: Specific floor number
    - has_images: 'true' to only return listings with images
    
    Geo Filtering:
    - lat, lng, radius_km: Find listings within radius of a point
    - bbox: "minLon,minLat,maxLon,maxLat" bounding box
    
    Pagination & Ordering:
    - limit: Max results (default 50, max 200)
    - offset: Skip first N results
    - order_by: 'price', '-price', 'date', '-date', 'sqft', '-sqft'
    
    Output Control:
    - format: 'summary' (default) or 'full'
    - include_images: 'true' or 'false' (for full format)
    
    Returns:
    --------
    {
        "success": true,
        "count": <total matching>,
        "returned": <number in this response>,
        "offset": <current offset>,
        "has_more": <boolean>,
        "filters_applied": {...},
        "results": [...]
    }
    """
    
    qs = Listing.objects.filter(is_published=True)
    filters_applied = {}
    
    # Deal Type Filter
    deal_type = request.GET.get('deal_type')
    if deal_type in ['kiralik', 'satis']:
        qs = qs.filter(deal_type=deal_type)
        filters_applied['deal_type'] = deal_type
    
    # Property Type Filter
    property_type = request.GET.get('property_type')
    if property_type:
        qs = qs.filter(property_type__icontains=property_type)
        filters_applied['property_type'] = property_type
    
    # Location Filters
    city = request.GET.get('city')
    if city:
        qs = qs.filter(city__icontains=city)
        filters_applied['city'] = city
    
    state = request.GET.get('state')
    if state:
        qs = qs.filter(state__icontains=state)
        filters_applied['state'] = state
    
    # Price Range
    try:
        min_price = request.GET.get('min_price')
        if min_price:
            qs = qs.filter(price__gte=int(min_price))
            filters_applied['min_price'] = int(min_price)
    except (ValueError, TypeError):
        pass
    
    try:
        max_price = request.GET.get('max_price')
        if max_price:
            qs = qs.filter(price__lte=int(max_price))
            filters_applied['max_price'] = int(max_price)
    except (ValueError, TypeError):
        pass
    
    # Bedroom filter (exact match on text like "1+0", "2+1")
    try:
        bedrooms = request.GET.get('bedrooms', '').strip()
        if bedrooms:
            qs = qs.filter(bedrooms=bedrooms)
            filters_applied['bedrooms'] = bedrooms
    except (ValueError, TypeError):
        pass
    
    # Bathroom Range
    try:
        min_bathrooms = request.GET.get('min_bathrooms')
        if min_bathrooms:
            qs = qs.filter(bathrooms__gte=int(min_bathrooms))
            filters_applied['min_bathrooms'] = int(min_bathrooms)
    except (ValueError, TypeError):
        pass
    
    try:
        max_bathrooms = request.GET.get('max_bathrooms')
        if max_bathrooms:
            qs = qs.filter(bathrooms__lte=int(max_bathrooms))
            filters_applied['max_bathrooms'] = int(max_bathrooms)
    except (ValueError, TypeError):
        pass
    
    # Square Footage / M2 Range
    try:
        min_sqft = request.GET.get('min_sqft')
        if min_sqft:
            qs = qs.filter(sqft__gte=int(min_sqft))
            filters_applied['min_sqft'] = int(min_sqft)
    except (ValueError, TypeError):
        pass
    
    try:
        max_sqft = request.GET.get('max_sqft')
        if max_sqft:
            qs = qs.filter(sqft__lte=int(max_sqft))
            filters_applied['max_sqft'] = int(max_sqft)
    except (ValueError, TypeError):
        pass
    
    try:
        min_m2 = request.GET.get('min_m2')
        if min_m2:
            qs = qs.filter(m2_net__gte=int(min_m2))
            filters_applied['min_m2'] = int(min_m2)
    except (ValueError, TypeError):
        pass
    
    try:
        max_m2 = request.GET.get('max_m2')
        if max_m2:
            qs = qs.filter(m2_net__lte=int(max_m2))
            filters_applied['max_m2'] = int(max_m2)
    except (ValueError, TypeError):
        pass
    
    # Rooms configuration
    rooms = request.GET.get('rooms')
    if rooms:
        qs = qs.filter(rooms_text__icontains=rooms)
        filters_applied['rooms'] = rooms
    
    # Boolean Filters
    furnished = request.GET.get('furnished')
    if furnished == 'true':
        qs = qs.filter(furnished=True)
        filters_applied['furnished'] = True
    elif furnished == 'false':
        qs = qs.filter(furnished=False)
        filters_applied['furnished'] = False
    
    elevator = request.GET.get('elevator')
    if elevator == 'true':
        qs = qs.filter(elevator=True)
        filters_applied['elevator'] = True
    elif elevator == 'false':
        qs = qs.filter(elevator=False)
        filters_applied['elevator'] = False
    
    parking = request.GET.get('parking')
    if parking == 'true':
        qs = qs.exclude(Q(parking_area='') | Q(parking_area__isnull=True))
        filters_applied['parking'] = True
    
    in_complex = request.GET.get('in_complex')
    if in_complex == 'true':
        qs = qs.filter(in_complex=True)
        filters_applied['in_complex'] = True
    elif in_complex == 'false':
        qs = qs.filter(in_complex=False)
        filters_applied['in_complex'] = False
    
    # Building Age
    try:
        max_building_age = request.GET.get('max_building_age')
        if max_building_age:
            qs = qs.filter(building_age__lte=int(max_building_age))
            filters_applied['max_building_age'] = int(max_building_age)
    except (ValueError, TypeError):
        pass
    
    # Floor
    try:
        floor = request.GET.get('floor')
        if floor:
            qs = qs.filter(floor_number=int(floor))
            filters_applied['floor'] = int(floor)
    except (ValueError, TypeError):
        pass
    
    # Has Images Filter
    has_images = request.GET.get('has_images')
    if has_images == 'true':
        qs = qs.filter(images__is_visible=True).distinct()
        filters_applied['has_images'] = True
    
    # Geo Filtering - Bounding Box
    bbox = request.GET.get('bbox')
    if bbox:
        try:
            min_lon, min_lat, max_lon, max_lat = [float(x.strip()) for x in bbox.split(',')]
            qs = qs.filter(
                latitude__gte=min_lat,
                latitude__lte=max_lat,
                longitude__gte=min_lon,
                longitude__lte=max_lon,
            )
            filters_applied['bbox'] = bbox
        except Exception:
            pass
    
    # Geo Filtering - Radius (approximate using lat/lng degrees)
    lat = request.GET.get('lat')
    lng = request.GET.get('lng')
    radius_km = request.GET.get('radius_km')
    if lat and lng and radius_km:
        try:
            lat = float(lat)
            lng = float(lng)
            radius_km = float(radius_km)
            # Approximate: 1 degree latitude ≈ 111 km
            lat_delta = radius_km / 111.0
            # Longitude varies by latitude
            lng_delta = radius_km / (111.0 * abs(cos(radians(lat))) if lat != 0 else 111.0)
            
            qs = qs.filter(
                latitude__gte=lat - lat_delta,
                latitude__lte=lat + lat_delta,
                longitude__gte=lng - lng_delta,
                longitude__lte=lng + lng_delta,
            )
            filters_applied['geo_center'] = {'lat': lat, 'lng': lng, 'radius_km': radius_km}
        except Exception:
            pass
    
    # Ordering
    order_by = request.GET.get('order_by', '-list_date')
    order_map = {
        'price': 'price',
        '-price': '-price',
        'date': 'list_date',
        '-date': '-list_date',
        'sqft': 'sqft',
        '-sqft': '-sqft',
        'bedrooms': 'bedrooms',
        '-bedrooms': '-bedrooms',
    }
    if order_by in order_map:
        qs = qs.order_by(order_map[order_by])
        filters_applied['order_by'] = order_by
    else:
        qs = qs.order_by('-list_date')
    
    # Get total count before pagination
    total_count = qs.count()
    
    # Pagination
    try:
        limit = min(int(request.GET.get('limit', 50)), 200)
    except (ValueError, TypeError):
        limit = 50
    
    try:
        offset = int(request.GET.get('offset', 0))
    except (ValueError, TypeError):
        offset = 0
    
    qs = qs[offset:offset + limit]
    
    # Format output
    output_format = request.GET.get('format', 'summary')
    include_images = request.GET.get('include_images', 'true').lower() == 'true'
    
    if output_format == 'full':
        results = [_listing_to_full_dict(request, listing, include_images=include_images) for listing in qs]
    else:
        results = [_listing_to_summary_dict(request, listing) for listing in qs]
    
    response_data = {
        'success': True,
        'count': total_count,
        'returned': len(results),
        'offset': offset,
        'limit': limit,
        'has_more': (offset + len(results)) < total_count,
        'filters_applied': filters_applied,
        'results': results,
    }
    
    resp = JsonResponse(response_data, json_dumps_params={'ensure_ascii': False})
    resp['Access-Control-Allow-Origin'] = '*'
    resp['Access-Control-Allow-Methods'] = 'GET'
    resp['Access-Control-Allow-Headers'] = 'Content-Type'
    return resp


@require_GET
def chatbot_listing_detail(request: HttpRequest, pk: int) -> JsonResponse:
    """
    Get full details of a single listing by ID.
    
    Path Parameters:
    - pk: Listing ID
    
    Query Parameters:
    - include_images: 'true' (default) or 'false'
    
    Returns full listing data including all fields and images.
    """
    try:
        listing = Listing.objects.get(pk=pk, is_published=True)
    except Listing.DoesNotExist:
        resp = JsonResponse({
            'success': False,
            'error': 'Listing not found',
            'error_code': 'NOT_FOUND'
        }, status=404)
        resp['Access-Control-Allow-Origin'] = '*'
        return resp
    
    include_images = request.GET.get('include_images', 'true').lower() == 'true'
    
    resp = JsonResponse({
        'success': True,
        'listing': _listing_to_full_dict(request, listing, include_images=include_images)
    }, json_dumps_params={'ensure_ascii': False})
    resp['Access-Control-Allow-Origin'] = '*'
    return resp


@require_GET
def chatbot_listings_stats(request: HttpRequest) -> JsonResponse:
    """
    Get statistics about available listings for AI context.
    
    Query Parameters:
    - deal_type: Filter stats by deal type ('kiralik' or 'satis')
    - city: Filter stats by city
    
    Returns aggregate statistics useful for AI to understand the inventory.
    """
    qs = Listing.objects.filter(is_published=True)
    
    # Optional filters
    deal_type = request.GET.get('deal_type')
    if deal_type in ['kiralik', 'satis']:
        qs = qs.filter(deal_type=deal_type)
    
    city = request.GET.get('city')
    if city:
        qs = qs.filter(city__icontains=city)
    
    # Aggregate stats
    stats = qs.aggregate(
        total_count=Count('id'),
        min_price=Min('price'),
        max_price=Max('price'),
        avg_price=Avg('price'),
        min_sqft=Min('sqft'),
        max_sqft=Max('sqft'),
        avg_sqft=Avg('sqft'),
    )
    bedroom_values = sorted(qs.values_list('bedrooms', flat=True).distinct())
    
    # Count by deal type
    by_deal_type = list(
        Listing.objects.filter(is_published=True)
        .values('deal_type')
        .annotate(count=Count('id'))
    )
    
    # Count by city (top 10)
    by_city = list(
        qs.values('city')
        .annotate(count=Count('id'))
        .order_by('-count')[:10]
    )
    
    # Count by property type
    by_property_type = list(
        qs.exclude(property_type='')
        .values('property_type')
        .annotate(count=Count('id'))
        .order_by('-count')[:10]
    )
    
    # Count by bedroom count
    by_bedrooms = list(
        qs.values('bedrooms')
        .annotate(count=Count('id'))
        .order_by('bedrooms')
    )
    
    # Price ranges
    price_ranges = {
        'under_10k': qs.filter(price__lt=10000).count(),
        '10k_25k': qs.filter(price__gte=10000, price__lt=25000).count(),
        '25k_50k': qs.filter(price__gte=25000, price__lt=50000).count(),
        '50k_100k': qs.filter(price__gte=50000, price__lt=100000).count(),
        '100k_250k': qs.filter(price__gte=100000, price__lt=250000).count(),
        '250k_500k': qs.filter(price__gte=250000, price__lt=500000).count(),
        '500k_1m': qs.filter(price__gte=500000, price__lt=1000000).count(),
        'over_1m': qs.filter(price__gte=1000000).count(),
    }
    
    # Features availability
    features = {
        'with_elevator': qs.filter(elevator=True).count(),
        'furnished': qs.filter(furnished=True).count(),
        'in_complex': qs.filter(in_complex=True).count(),
        'with_parking': qs.exclude(Q(parking_area='') | Q(parking_area__isnull=True)).count(),
        'with_images': qs.filter(images__is_visible=True).distinct().count(),
        'with_coordinates': qs.exclude(Q(latitude__isnull=True) | Q(longitude__isnull=True)).count(),
    }
    
    response_data = {
        'success': True,
        'statistics': {
            'total_listings': stats['total_count'],
            'price': {
                'min': stats['min_price'],
                'max': stats['max_price'],
                'avg': round(stats['avg_price']) if stats['avg_price'] else None,
                'ranges': price_ranges,
            },
            'size': {
                'min_sqft': stats['min_sqft'],
                'max_sqft': stats['max_sqft'],
                'avg_sqft': round(stats['avg_sqft']) if stats['avg_sqft'] else None,
            },
            'bedrooms': {
                'values': bedroom_values,
                'distribution': by_bedrooms,
            },
            'by_deal_type': by_deal_type,
            'by_city': by_city,
            'by_property_type': by_property_type,
            'features': features,
        },
        'filters_applied': {
            'deal_type': deal_type,
            'city': city,
        }
    }
    
    resp = JsonResponse(response_data, json_dumps_params={'ensure_ascii': False})
    resp['Access-Control-Allow-Origin'] = '*'
    return resp


@require_GET
def chatbot_locations(request: HttpRequest) -> JsonResponse:
    """
    Get available locations (cities and states) for AI to know what areas are covered.
    
    Returns unique cities and states/districts with listing counts.
    """
    qs = Listing.objects.filter(is_published=True)
    
    # Get unique cities with counts
    cities = list(
        qs.exclude(city='')
        .values('city')
        .annotate(count=Count('id'))
        .order_by('-count')
    )
    
    # Get unique states/districts with counts
    states = list(
        qs.exclude(state='')
        .values('state', 'city')
        .annotate(count=Count('id'))
        .order_by('city', '-count')
    )
    
    # Group states by city
    states_by_city = {}
    for s in states:
        city = s['city']
        if city not in states_by_city:
            states_by_city[city] = []
        states_by_city[city].append({
            'state': s['state'],
            'count': s['count']
        })
    
    response_data = {
        'success': True,
        'locations': {
            'cities': cities,
            'districts_by_city': states_by_city,
        },
        'total_cities': len(cities),
        'total_unique_districts': len(set(s['state'] for s in states if s['state'])),
    }
    
    resp = JsonResponse(response_data, json_dumps_params={'ensure_ascii': False})
    resp['Access-Control-Allow-Origin'] = '*'
    return resp


@require_GET
def chatbot_api_docs(request: HttpRequest) -> JsonResponse:
    """
    Return API documentation for AI chatbots to understand available endpoints.
    """
    base_url = _get_base_url(request)
    
    docs = {
        'name': 'Kuzey Emlak Chatbot API',
        'version': '1.0.0',
        'description': 'Read-only API endpoints for AI chatbots to query real estate listings.',
        'base_url': base_url,
        
        'endpoints': [
            {
                'path': '/api/bot/search',
                'method': 'GET',
                'description': 'Search and filter listings with extensive filtering options',
                'parameters': {
                    'filtering': {
                        'deal_type': "Filter by 'kiralik' (rent) or 'satis' (sale)",
                        'property_type': 'Property type (e.g., Daire, Villa)',
                        'city': 'City name (partial match)',
                        'state': 'District/state name (partial match)',
                        'min_price/max_price': 'Price range in TL',
                        'min_bedrooms/max_bedrooms': 'Bedroom count range',
                        'min_m2/max_m2': 'Square meter range',
                        'rooms': "Room configuration (e.g., '2+1', '3+1')",
                        'furnished': "'true' or 'false'",
                        'elevator': "'true' or 'false'",
                        'parking': "'true' if must have parking",
                        'in_complex': "'true' or 'false'",
                        'max_building_age': 'Maximum building age in years',
                    },
                    'geo': {
                        'bbox': 'Bounding box: minLon,minLat,maxLon,maxLat',
                        'lat/lng/radius_km': 'Center point and radius for proximity search',
                    },
                    'pagination': {
                        'limit': 'Max results (default 50, max 200)',
                        'offset': 'Skip first N results',
                        'order_by': "Sort by: 'price', '-price', 'date', '-date', 'sqft', '-sqft'",
                    },
                    'output': {
                        'format': "'summary' (default) or 'full'",
                        'include_images': "'true' or 'false' (for full format)",
                    },
                },
                'example': f'{base_url}/api/bot/search?city=istanbul&deal_type=kiralik&max_price=20000&min_bedrooms=2',
            },
            {
                'path': '/api/bot/listing/<id>',
                'method': 'GET',
                'description': 'Get full details of a single listing by ID',
                'parameters': {
                    'include_images': "'true' (default) or 'false'",
                },
                'example': f'{base_url}/api/bot/listing/123',
            },
            {
                'path': '/api/bot/stats',
                'method': 'GET',
                'description': 'Get aggregate statistics about available listings',
                'parameters': {
                    'deal_type': "Filter stats by 'kiralik' or 'satis'",
                    'city': 'Filter stats by city',
                },
                'example': f'{base_url}/api/bot/stats?deal_type=kiralik',
            },
            {
                'path': '/api/bot/locations',
                'method': 'GET',
                'description': 'Get list of available cities and districts',
                'example': f'{base_url}/api/bot/locations',
            },
        ],
        
        'notes': [
            'All endpoints are read-only (GET requests only)',
            'All endpoints return JSON with CORS headers enabled',
            'Image URLs are absolute and directly accessible',
            'Prices are in Turkish Lira (TL)',
            'All text fields support Turkish characters',
        ],
        
        'deal_types': {
            'kiralik': 'For Rent',
            'satis': 'For Sale',
        },
        
        'common_property_types': [
            'Daire',
            'Residence',
            'Villa',
            'Müstakil Ev',
            'Yazlık',
        ],
    }
    
    resp = JsonResponse(docs, json_dumps_params={'ensure_ascii': False, 'indent': 2})
    resp['Access-Control-Allow-Origin'] = '*'
    return resp


# Import math functions for geo calculations
from math import cos, radians
import os


@require_GET
def chatbot_openapi_spec(request: HttpRequest) -> JsonResponse:
    """
    Return the OpenAPI 3.1 specification for the Chatbot API.
    """
    spec_path = os.path.join(os.path.dirname(__file__), 'chatbot_openapi.json')
    
    try:
        with open(spec_path, 'r', encoding='utf-8') as f:
            spec = json.load(f)
        
        # Update server URL to match current request
        base_url = _get_base_url(request)
        spec['servers'] = [
            {'url': base_url, 'description': 'Current server'},
            {'url': 'https://kuzey-emlak.lotfinity.tech', 'description': 'Production server'}
        ]
        
        resp = JsonResponse(spec, json_dumps_params={'ensure_ascii': False, 'indent': 2})
        resp['Access-Control-Allow-Origin'] = '*'
        return resp
    except Exception as e:
        resp = JsonResponse({
            'error': 'Failed to load OpenAPI spec',
            'detail': str(e)
        }, status=500)
        resp['Access-Control-Allow-Origin'] = '*'
        return resp
