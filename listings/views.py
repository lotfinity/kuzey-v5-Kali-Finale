from django.shortcuts import render, redirect, get_object_or_404
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.http import HttpResponse, JsonResponse
from django.conf import settings
from django.views.decorators.clickjacking import xframe_options_exempt
from django.db.models import Min, Max
import re, json
import urllib.request
from urllib.error import HTTPError, URLError

from listings.choices import price_choices , bedroom_choices , state_choices, type_choices, rentability_group_choices

from .models import AirbnbListing, Listing
from .investor import DEFAULT_INVESTOR_SETTINGS, airbnb_comp_records, build_investor_summary, investor_settings_from_request, score_listing
from .portfolio import build_listing_portfolio_context

EXTERNAL_AMENITIES_BASE = 'http://100.89.48.48:8006/map/amenities/'

# Create your views here
def sort_listings_for_index(listings, sort='best'):
    sort = (sort or 'best').strip()
    sort_options = {
        'price_asc': 'price',
        'price_desc': '-price',
        'size_asc': 'm2_gross',
        'size_desc': '-m2_gross',
        'date_asc': 'list_date',
        'date_desc': '-list_date',
    }
    if sort != 'best':
        return listings.order_by(sort_options.get(sort, '-list_date')), sort

    comps = airbnb_comp_records()
    scored = []
    for listing in listings:
        try:
            score = score_listing(listing, comps, DEFAULT_INVESTOR_SETTINGS)["risk_adjusted_score"]
        except Exception:
            score = 0
        scored.append((score, listing.price or 0, listing))
    return [item[2] for item in sorted(scored, key=lambda item: (item[0], -item[1]), reverse=True)], 'best'


def index(request):
	return new_properties(request)


def home_wizard(request):
    """Landing page: one-time wizard (lang → currency → theme) then stats dashboard."""
    wizard_cookie = request.COOKIES.get('kuzey_wizard')

    if wizard_cookie and request.method == 'GET':
        try:
            prefs = json.loads(wizard_cookie)
        except (json.JSONDecodeError, TypeError):
            prefs = None
        if prefs and all(k in prefs for k in ('lang', 'currency', 'theme')):
            listings = Listing.objects.filter(is_published=True)
            total = listings.count()
            stats = listings.aggregate(
                smallest_m2=Min('m2_gross'),
                biggest_m2=Max('m2_gross'),
                cheapest=Min('price'),
                most_expensive=Max('price'),
            )
            under_125 = listings.filter(price__lte=1250000).count()
            over_125 = listings.filter(price__gte=1250000).count()

            return render(request, 'newfrontend/index.html', {
                'wizard_done': True,
                'total_listings': total,
                'stats': stats,
                'under_125_count': under_125,
                'over_125_count': over_125,
                'wizard_prefs': prefs,
            })

    if request.method == 'POST':
        lang = request.POST.get('language', settings.LANGUAGE_CODE)
        currency = request.POST.get('currency', 'TRY')
        theme = request.POST.get('theme', 'dark')

        wizard_data = json.dumps({'lang': lang, 'currency': currency, 'theme': theme})
        response = redirect('home_wizard')
        response.set_cookie('kuzey_wizard', wizard_data, max_age=365*24*3600, path='/')
        return response

    return render(request, 'newfrontend/index.html', {
        'wizard_done': False,
    })


def rewrite_external_tile_layer(html):
    if 'tile.openstreetmap.org' not in html.lower():
        return html
    html = html.replace(
        "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
        "https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}.png"
    )
    html = html.replace(
        "© OpenStreetMap contributors",
        "© OpenStreetMap contributors, © CARTO"
    )
    # Ensure the tile layer sends a browser referrer if supported by Leaflet
    html = re.sub(
        r"(L\.tileLayer\([^,]+,\s*\{)([\s\S]*?)(\}\))",
        lambda m: m.group(1) + "\n            referrerPolicy: 'no-referrer-when-downgrade'," + m.group(2) + m.group(3),
        html,
        count=1
    )
    return html


def fetch_external_amenities_html(listing):
    if listing.latitude is None or listing.longitude is None:
        return None
    url = f"{EXTERNAL_AMENITIES_BASE}?q={listing.latitude},{listing.longitude}"
    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': 'CoralCity/1.0',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            if resp.status != 200:
                return None
            content_type = resp.headers.get('Content-Type', '')
            if 'text/html' not in content_type.lower():
                return None
            charset = resp.headers.get_content_charset('utf-8')
            html = resp.read().decode(charset, errors='replace')
            return rewrite_external_tile_layer(html)
    except (HTTPError, URLError, TimeoutError, ValueError):
        return None


def listing_portfolio(request, listing_id):
    listing = get_object_or_404(Listing, pk=listing_id)
    if listing.latitude is None or listing.longitude is None:
        return HttpResponse("This listing needs coordinates before a portfolio map can be rendered.", status=400)
    return render(request, "newfrontend/listing-portfolio.html", build_listing_portfolio_context(listing))


def new_properties(request, page=None, min_price=None, max_price=None, bedrooms=None, rentability_group=None):
    """Render the new frontend properties page with sorting toggles.

    Optional URL kwargs act as default filter values (used by prefiltered routes like
    /opportunities/under-1.25m/), overridden by explicit GET parameters.
    """
    listings = Listing.objects.filter(is_published=True)

    # --- Prefiltered URL kwargs (used by prefiltered routes) ---
    min_price = request.GET.get('min_price', min_price or '').strip()
    max_price = request.GET.get('max_price', max_price or '').strip()
    bedrooms = request.GET.get('bedrooms', bedrooms or '').strip()
    rentability_group = request.GET.get('rentability_group', rentability_group or '').strip()

    if min_price:
        try:
            listings = listings.filter(price__gte=int(min_price))
        except ValueError:
            pass
    if max_price:
        try:
            listings = listings.filter(price__lte=int(max_price))
        except ValueError:
            pass
    if bedrooms:
        listings = listings.filter(bedrooms=bedrooms)
    if rentability_group in rentability_group_choices:
        listings = listings.filter(rentability_groups__contains=rentability_group)

    sort = request.GET.get('sort', 'best').strip()
    listings, sort = sort_listings_for_index(listings, sort)

    paginator = Paginator(listings, 12)
    raw = page if page is not None else request.GET.get('page')
    try:
        page_num = int(raw) if raw is not None else 1
    except (TypeError, ValueError):
        page_num = 1
    if page_num < 1:
        page_num = 1
    paged_listings = paginator.get_page(page_num)

    db_bedrooms = sorted(Listing.objects.filter(is_published=True).values_list('bedrooms', flat=True).distinct())
    price_agg = Listing.objects.filter(is_published=True).aggregate(lo=Min('price'), hi=Max('price'))
    price_min = price_agg['lo'] or 0
    price_max = price_agg['hi'] or 0

    qd = request.GET.copy()
    if 'page' in qd:
        del qd['page']
    sort_qd = qd.copy()
    if 'sort' in sort_qd:
        del sort_qd['sort']
    querystring = qd.urlencode()
    sort_query_base = sort_qd.urlencode()

    return render(request, 'newfrontend/properties.html', {
        'listings': paged_listings,
        'values': request.GET,
        'bedroom_choices': db_bedrooms,
        'rentability_group_choices': rentability_group_choices,
        'price_min': price_min,
        'price_max': price_max,
        'sort': sort,
        'querystring': querystring,
        'sort_query_base': sort_query_base,
    })


def new_listing_detail(request, listing_id):
        listing = get_object_or_404(Listing, pk=listing_id)
        # Keep generated map HTML isolated. The map snippets include page-level
        # html/body CSS for standalone use, so inlining them can lock scrolling
        # on the listing detail page.
        map_embed_html = None

        return render(request, 'newfrontend/property-details.html', {'listing': listing, 'map_embed_html': map_embed_html})


def new_property_details_preview(request):
    """Preview page for new property details without specifying an ID.

    - If there is a published listing, render that.
    - Otherwise, render a lightweight demo listing so templates don't fail.
    This supports static builds (django-distill) where a fixed route exists.
    """
    listing = Listing.objects.filter(is_published=True).order_by('-list_date').first()
    if not listing:
        # Build a simple stand-in object with the attributes used by the template
        from types import SimpleNamespace
        listing = SimpleNamespace(
            id=0,
            title="Sample Property",
            address="123 Demo Street",
            description="Demo property for preview.",
            deal_type="kiralik",
            property_type=" Apartment",
            city="Istanbul",
            state="TR",
            price=0,
            bedrooms="",
            bathrooms=0,
            m2_gross=None,
            m2_net=None,
            rooms_text="",
            building_age=None,
            floor_number=None,
            floors_total=None,
            heating="",
            kitchen_type="",
            balcony="",
            parking_area="",
            usage_status="",
            in_complex=None,
            complex_name="",
            elevator=None,
            furnished=None,
            maintenance_fee=None,
            deposit=None,
            deed_status="",
            from_whom="",
            external_id=None,
            ad_date=None,
            list_date=None,
            rentability_group_labels=[],
            visible_images=[],
        )
    return render(request, 'newfrontend/property-details.html', {'listing': listing})


def listing(request , listing_id):
	listing = get_object_or_404(Listing , pk=listing_id)
	context = {
	  'listing' : listing
	}
	return render(request,'listings/listing.html',context)


def search(request):
	queryset_list = Listing.objects.order_by('-list_date')
	if 'keywords' in request.GET:
		keywords = request.GET['keywords']
		if keywords:
			queryset_list = queryset_list.filter(description__icontains=keywords)

	if 'city' in request.GET:
		city = request.GET['city']
		if city:
			queryset_list = queryset_list.filter(city__iexact=city)

	if 'state' in request.GET:
		state = request.GET['state']
		if state:
			queryset_list = queryset_list.filter(state__iexact=state)

	if 'bedrooms' in request.GET:
		bedrooms = request.GET['bedrooms']
		if bedrooms:
			queryset_list = queryset_list.filter(bedrooms=bedrooms)

	if 'price' in request.GET:
		price = request.GET['price']
		if price:
			queryset_list = queryset_list.filter(price__lte=price)


	return render(request,'listings/search.html',{
		'listings' : queryset_list,
        'state_choices' : state_choices,
        'bedroom_choices' : bedroom_choices,
        'price_choices' : price_choices,
        'type_choices' : type_choices,
        'values': request.GET,
		})


def map_view(request):
    return render(request, 'listings/map.html')


def map_data(request):
    # Get initial queryset and check total count
    qs = Listing.objects.filter(is_published=True)
    initial_count = qs.count()
    print(f"Initial published listings count: {initial_count}")

    # Check how many have coordinates
    has_coords = qs.exclude(latitude__isnull=True).exclude(longitude__isnull=True).count()
    print(f"Listings with coordinates: {has_coords}")

    # Print a sample of listings to check coordinate values
    sample = qs[:5]
    print("\nSample listings:")
    for listing in sample:
        print(f"ID: {listing.id}, Title: {listing.title}, Lat: {listing.latitude}, Lng: {listing.longitude}")

    # Optional filters to mirror search behavior
    keywords = request.GET.get('keywords')
    if keywords:
        qs = qs.filter(description__icontains=keywords)

    city = request.GET.get('city')
    if city:
        qs = qs.filter(city__iexact=city)

    state = request.GET.get('state')
    if state:
        qs = qs.filter(state__iexact=state)

    bedrooms = request.GET.get('bedrooms')
    if bedrooms:
        qs = qs.filter(bedrooms=bedrooms)

    price = request.GET.get('price')
    if price:
        qs = qs.filter(price__lte=price)

    # Filter for listings with non-null coordinates (further validated below)
    qs = qs.exclude(latitude__isnull=True).exclude(longitude__isnull=True)
    final_count = qs.count()
    print(f"\nFinal filtered listings count: {final_count}")

    def _valid_coord(lat, lng):
        try:
            latf = float(lat)
            lngf = float(lng)
        except (TypeError, ValueError):
            return False
        if not (-90.0 <= latf <= 90.0 and -180.0 <= lngf <= 180.0):
            return False
        # Heuristic: skip obviously placeholder zeros
        if latf == 0.0 and lngf == 0.0:
            return False
        return True

    features = []
    skipped_invalid = 0
    for obj in qs:
        if not _valid_coord(obj.latitude, obj.longitude):
            skipped_invalid += 1
            continue
        properties = {
            "id": obj.id,
            "title": obj.title,
            "price": obj.price,
            "estimated_monthly_rent": obj.estimated_rent,
            "estimated_monthly_rent_try": obj.estimated_monthly_rent_try,
            "rent_estimate_source": obj.rent_estimate_source,
            "rent_estimate_updated_at": obj.rent_estimate_updated_at.isoformat() if obj.rent_estimate_updated_at else None,
            "airbnb_comp_count": obj.airbnb_comp_count,
            "airbnb_comp_median": obj.airbnb_comp_median_try,
            "bedrooms": obj.bedrooms,
            "bathrooms": obj.bathrooms,
            "property_type": obj.property_type,
            "deal_type": obj.deal_type,
            "rooms_text": obj.rooms_text,
            "m2_net": obj.m2_net,
            "m2_gross": obj.m2_gross,
            "city": obj.city,
            "state": obj.state,
            "address": obj.address,
            "url": f"/listings/{obj.id}/",
        }
        # Collect available photos for swipeable gallery in popup from related images
        photos = []
        try:
            for img in obj.images.order_by('order', 'id'):
                if getattr(img, 'image', None):
                    photos.append(img.image.url)
        except Exception:
            pass
        if photos:
            properties["photos"] = photos
            # Keep legacy single photo key for backward-compat
            properties["photo_url"] = photos[0]

        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [float(obj.longitude), float(obj.latitude)],
            },
            "properties": properties,
        })

    resp = {
        "type": "FeatureCollection",
        "features": features,
    }
    if skipped_invalid:
        resp["skipped_invalid"] = skipped_invalid
    return JsonResponse(resp)


def airbnb_map_data(request):
    qs = AirbnbListing.objects.exclude(latitude__isnull=True).exclude(longitude__isnull=True)

    destination = request.GET.get('destination') or 'Esenyurt, Istanbul, Turkey'
    if destination:
        qs = qs.filter(source_destination_query__iexact=destination)

    def _valid_coord(lat, lng):
        try:
            latf = float(lat)
            lngf = float(lng)
        except (TypeError, ValueError):
            return False
        return -90.0 <= latf <= 90.0 and -180.0 <= lngf <= 180.0 and not (latf == 0.0 and lngf == 0.0)

    features = []
    skipped_invalid = 0
    for obj in qs.order_by('rank', '-overall_rating', 'title'):
        if not _valid_coord(obj.latitude, obj.longitude):
            skipped_invalid += 1
            continue
        price = obj.total_cost if obj.total_cost is not None else obj.nightly_rate
        properties = {
            "id": obj.listing_id,
            "source": "airbnb",
            "title": obj.title,
            "tagline": obj.tagline,
            "price": float(price) if price is not None else None,
            "nightly_rate": float(obj.nightly_rate) if obj.nightly_rate is not None else None,
            "total_cost": float(obj.total_cost) if obj.total_cost is not None else None,
            "currency": obj.currency or "USD",
            "price_qualifier": "July stay",
            "property_type": obj.property_type,
            "bedrooms": obj.bedroom_count,
            "bathrooms": float(obj.bathroom_count) if obj.bathroom_count is not None else None,
            "bed_count": obj.bed_count,
            "guest_capacity": obj.guest_capacity,
            "rooms_text": "",
            "city": obj.city,
            "state": obj.location or obj.full_address,
            "address": obj.full_address or obj.location,
            "listing_url": obj.listing_url,
            "booking_url": obj.booking_url or obj.listing_url,
            "url": obj.booking_url or obj.listing_url,
            "photos": obj.photos or [],
            "overall_rating": float(obj.overall_rating) if obj.overall_rating is not None else None,
            "review_count": obj.review_count,
            "is_superhost": obj.is_superhost,
            "is_guest_favorite": obj.is_guest_favorite,
            "is_rare_find": obj.is_rare_find,
            "rank": obj.rank,
            "pricing": obj.pricing or {},
        }
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [float(obj.longitude), float(obj.latitude)],
            },
            "properties": properties,
        })

    resp = {
        "type": "FeatureCollection",
        "features": features,
        "total_results": qs.count(),
    }
    if skipped_invalid:
        resp["skipped_invalid"] = skipped_invalid
    return JsonResponse(resp)


def new_map_view(request):
	"""Render the new frontend map page."""
	return render(request, 'newfrontend/map.html')


def investor_medical_rentals(request):
    """Render the private investor decision dashboard."""
    return render(request, 'newfrontend/investor_medical_rentals.html')


def investor_medical_rentals_summary(request):
    """JSON summary for the investor decision dashboard."""
    return JsonResponse(build_investor_summary(investor_settings_from_request(request)))


def new_maplibre_view(request):
	"""Render the experimental MapLibre frontend map page."""
	return render(request, 'newfrontend/maplibre.html')


def new_map_view_copy(request):
	"""Render the duplicate new frontend map page."""
	return render(request, 'newfrontend/map_copy.html')


def whatsapp_inbox(request):
    """Standalone WhatsApp conversation workspace for hunt-related messages."""
    return render(request, 'newfrontend/whatsapp_inbox.html')


@xframe_options_exempt
def listing_map_embed(request, listing_id: int):
    """Render the pre-generated Leaflet map HTML for a specific listing.

    - Loads newfrontend/maps/listing_<id>.html (or _map_only fallback)
    - Injects enhancement styles and a light info panel fed by DATA
    - Returns full HTML in an iframe-safe response
    """
    from django.template.loader import select_template
    print(f"[map-embed] Incoming request: listing_id={listing_id}")
    try:
        template = select_template([
            f'newfrontend/maps/listing_{listing_id}.html',
            f'newfrontend/maps/listing_{listing_id}_map_only.html',
        ])
    except Exception:
        print(f"[map-embed] No template found for listing_id={listing_id}")
        listing = get_object_or_404(Listing, pk=listing_id)
        external_html = fetch_external_amenities_html(listing)
        if external_html:
            response = HttpResponse(external_html)
            response['Cross-Origin-Opener-Policy'] = 'unsafe-none'
            response['X-Map-Embed'] = 'proxy-external-amenities'
            response['X-Map-Embed-Source'] = 'external_amenities'
            return response
        return render(request, 'newfrontend/page-404.html', status=404)
    # Try to log selected template name for visibility
    try:
        tname = getattr(template, 'template', None)
        tname = getattr(tname, 'name', None) or getattr(template, 'name', 'unknown')
    except Exception:
        tname = 'unknown'
    print(f"[map-embed] Using template: {tname}")

    html = template.render({}, request)
    print(f"[map-embed] Rendered HTML length: {len(html)} bytes")
    has_data_literal = ('const DATA' in html) or ('window.DATA' in html)
    print(f"[map-embed] DATA present in HTML: {has_data_literal}")

    # Enhancement CSS from user (scoped to iframe)
    css = r"""
    /* injected-map-enhancements */
    /* Info Panel */
    .info-panel { position:absolute; top:10px; right:10px; z-index:1000; max-height:80vh; overflow-y:auto; background:#fff; border-radius:.75rem; box-shadow:0 10px 15px -3px rgba(0,0,0,.1),0 4px 6px -2px rgba(0,0,0,.05); min-width:300px; max-width:400px; opacity:0; visibility:hidden; transition:opacity .3s ease, visibility .3s ease; }
    .info-panel.is-visible { opacity:1; visibility:visible; }
    .info-panel-header { background:#667eea; padding:.75rem 1rem; border-bottom:1px solid #e5e7eb; }
    .info-panel-title { margin:0; color:#fff; font-size:1rem; font-weight:600; }
    .info-panel-body { font-size:.875rem; padding:1rem; }
    .info-section { margin-bottom:1rem; }
    .info-section:last-child { margin-bottom:0; }
    .info-section-title { font-weight:600; color:#667eea; font-size:.75rem; text-transform:uppercase; margin-bottom:.5rem; padding-bottom:.25rem; border-bottom:1px solid #e5e7eb; }
    .info-item { padding:.25rem 0; font-size:.875rem; color:#4b5563; }
    .info-item strong { color:#1f2937; font-weight:600; }
    /* Custom Leaflet Marker Styling */
    .listing-photo-marker img { transition:all .2s ease; }
    .listing-photo-marker img:hover { filter:brightness(1.1) contrast(1.1); box-shadow:0 4px 12px rgba(0,0,0,.4); }
    .leaflet-marker { transition:opacity .3s ease; }
    /* Swiper styles for listing popup carousel */
    .listing-swiper { width:100%; height:250px; border-radius:8px; overflow:hidden; margin-bottom:12px; }
    .listing-swiper .swiper-slide { display:flex; align-items:center; justify-content:center; background:#f0f0f0; }
    .listing-swiper img { width:100%; height:100%; object-fit:cover; }
    .swiper-pagination { position:relative !important; margin-top:8px; }
    .swiper-pagination-bullet { background:#667eea !important; opacity:.6; }
    .swiper-pagination-bullet-active { opacity:1 !important; }
    /* Error message */
    .error-message { position:absolute; top:50%; left:50%; transform:translate(-50%,-50%); z-index:2000; min-width:300px; padding:1rem; border-radius:.5rem; background:#fef2f2; color:#991b1b; border:1px solid #fecaca; }

    /* Map Guide (bottom-left toggle + panel) */
    .map-guide-toggle { position:absolute; left:10px; bottom:10px; z-index:1001; border:0; padding:8px 10px; border-radius:9999px; background:#fff; color:#111827; box-shadow:0 2px 10px rgba(0,0,0,.15); cursor:pointer; font-size:12px; }
    .map-guide-toggle:hover { background:#f3f4f6; }
    .map-guide-panel { position:absolute; left:10px; bottom:56px; z-index:1001; background:#fff; border-radius:10px; padding:10px 12px; box-shadow:0 8px 24px rgba(0,0,0,.15); max-width:280px; display:none; }
    .map-guide-row { display:flex; align-items:center; gap:8px; margin:6px 0; font-size:13px; color:#111827; }
    .map-guide-dot { width:10px; height:10px; border-radius:50%; flex:0 0 auto; }
    """

    # Lightweight panel builder that uses DATA from the map HTML if present
    script = r"""
    <script id="injected-map-enhancements">(function(){
      try{
        var DATA = window.DATA || null;
        if(!DATA) return; // Nothing to present
        // Create panel container
        var panel = document.createElement('div');
        panel.className = 'info-panel is-visible';
        var header = document.createElement('div');
        header.className = 'info-panel-header';
        var h = document.createElement('h4');
        h.className = 'info-panel-title';
        h.textContent = (DATA.listing && DATA.listing.title ? DATA.listing.title : 'Listing Info');
        header.appendChild(h);
        var body = document.createElement('div');
        body.className = 'info-panel-body';

        function fmtMeters(m){ if(m == null) return '-'; var v = Math.round(m); return v < 1000 ? (v + ' m') : ((v/1000).toFixed(1) + ' km'); }
        function makeSection(title){ var d=document.createElement('div'); d.className='info-section'; var t=document.createElement('div'); t.className='info-section-title'; t.textContent=title; d.appendChild(t); return d; }
        function addItem(container, label, value){ var p=document.createElement('div'); p.className='info-item'; p.innerHTML = '<strong>'+label+':</strong> ' + (value==null?'-':value); container.appendChild(p); }

        // Listing basics
        var sec0 = makeSection('Listing');
        if (DATA.listing){
          addItem(sec0, 'Price', DATA.listing.price ? '₺'+DATA.listing.price.toLocaleString('tr-TR') : '-');
          if(DATA.listing.lat && DATA.listing.lng){ addItem(sec0, 'Coordinates', DATA.listing.lat.toFixed(6)+', '+DATA.listing.lng.toFixed(6)); }
        }
        body.appendChild(sec0);

        // Nearest metrobus
        if (Array.isArray(DATA.closest_metrobus) && DATA.closest_metrobus.length){
          var sec1 = makeSection('Nearest Metrobus');
          DATA.closest_metrobus.slice(0,3).forEach(function(m){ addItem(sec1, m.name, fmtMeters(m.distance_m)); });
          body.appendChild(sec1);
        }
        // Nearest bus stops
        if (Array.isArray(DATA.closest_bus_stops) && DATA.closest_bus_stops.length){
          var sec2 = makeSection('Nearest Bus Stops');
          DATA.closest_bus_stops.slice(0,3).forEach(function(s){ addItem(sec2, s.name, fmtMeters(s.distance_m)); });
          body.appendChild(sec2);
        }
        // Nearest grocery
        if (Array.isArray(DATA.closest_grocery_stores) && DATA.closest_grocery_stores.length){
          var sec3 = makeSection('Grocery Stores');
          DATA.closest_grocery_stores.slice(0,3).forEach(function(g){ addItem(sec3, g.name, fmtMeters(g.distance_m)); });
          body.appendChild(sec3);
        }

        panel.appendChild(header); panel.appendChild(body);
        document.body.appendChild(panel);

        // Amenities-focused popup at listing location (if Leaflet map is available)
        function mkList(items){ return '<ul style=\"margin:6px 0 0 16px; padding:0;\">'+items.map(function(i){return '<li>'+i+'</li>';}).join('')+'</ul>'; }
        function buildPopupHtml(){
          var html = '<div class=\"font-sans\" style=\"max-width:320px\">';
          html += '<div style=\"font-weight:700;margin-bottom:6px;color:#1f2937\">Nearby Amenities</div>';
          var rows = [];
          if (Array.isArray(DATA.closest_metrobus) && DATA.closest_metrobus.length){
            var topM = DATA.closest_metrobus.slice(0,2).map(function(m){ return m.name + ' • ' + fmtMeters(m.distance_m); });
            rows.push('<div><strong>Metrobus:</strong>'+ mkList(topM) +'</div>');
          }
          if (Array.isArray(DATA.closest_bus_stops) && DATA.closest_bus_stops.length){
            var topB = DATA.closest_bus_stops.slice(0,3).map(function(s){ return s.name + ' • ' + fmtMeters(s.distance_m); });
            rows.push('<div style=\"margin-top:6px\"><strong>Bus Stops:</strong>'+ mkList(topB) +'</div>');
          }
          if (Array.isArray(DATA.closest_grocery_stores) && DATA.closest_grocery_stores.length){
            var g0 = DATA.closest_grocery_stores[0];
            rows.push('<div style=\"margin-top:6px\"><strong>Grocery:</strong> '+ g0.name + ' • ' + fmtMeters(g0.distance_m) + '</div>');
          }
          if (Array.isArray(DATA.closest_clothing_stores) && DATA.closest_clothing_stores.length){
            var c0 = DATA.closest_clothing_stores[0];
            rows.push('<div style=\"margin-top:6px\"><strong>Clothing:</strong> '+ c0.name + ' • ' + fmtMeters(c0.distance_m) + '</div>');
          }
          if (!rows.length){ html += '<div>No nearby amenities data.</div>'; }
          else { html += rows.join(''); }
          html += '</div>';
          return html;
        }
        function tryAttachPopup(attempt){
          attempt = attempt || 0;
          if (attempt > 20) return; // ~2s
          try {
            if (window.L && window.map && DATA.listing && DATA.listing.lat && DATA.listing.lng){
              var content = buildPopupHtml();
              window.L.popup({autoPan:true, maxWidth: 320})
                .setLatLng([DATA.listing.lat, DATA.listing.lng])
                .setContent(content)
                .openOn(window.map);
              return;
            }
          } catch(e) { /* retry */ }
          setTimeout(function(){ tryAttachPopup(attempt+1); }, 100);
        }
        tryAttachPopup(0);
      }catch(e){ /* fail safe */ }
    })();</script>
    """

    # Small helper to add a bottom-left Map Guide legend with a toggle button
    guide_script = r"""
    <script id="injected-map-guide">(function(){
      function ready(fn){ if(document.readyState!=='loading'){ fn(); } else { document.addEventListener('DOMContentLoaded', fn); } }
      ready(function(){
        try{
          var mapEl = document.getElementById('map');
          if(!mapEl) return;
          if(mapEl.querySelector('.map-guide-toggle')) return; // prevent duplicates
          mapEl.style.position = mapEl.style.position || 'relative';
          var btn = document.createElement('button');
          btn.type='button'; btn.className='map-guide-toggle'; btn.textContent='Map guide';
          var panel = document.createElement('div'); panel.className='map-guide-panel';
          panel.innerHTML = [
            '<div class="map-guide-row"><span class="map-guide-dot" style="background:#1d4ed8"></span> Listing location</div>',
            '<div class="map-guide-row"><span class="map-guide-dot" style="background:#dc2626"></span> Metrobus stop</div>',
            '<div class="map-guide-row"><span class="map-guide-dot" style="background:#16a34a"></span> Bus stop</div>',
            '<div class="map-guide-row"><span class="map-guide-dot" style="background:#f59e0b"></span> Grocery</div>',
            '<div class="map-guide-row"><span class="map-guide-dot" style="background:#8b5cf6"></span> Clothing store</div>',
            '<div class="map-guide-row"><span class="map-guide-dot" style="background:#0ea5e9"></span> Taxi stand</div>',
            '<div class="map-guide-row"><span class="map-guide-dot" style="background:#6b7280"></span> Minibus line</div>',
            '<div class="map-guide-row"><span class="map-guide-dot" style="background:#22c55e"></span> Bicycle path</div>'
          ].join('');
          btn.addEventListener('click', function(){ panel.style.display = (panel.style.display==='none'||!panel.style.display) ? 'block' : 'none'; });
          panel.style.display='none';
          mapEl.appendChild(btn);
          mapEl.appendChild(panel);
        }catch(e){ /* ignore */ }
      });
    })();</script>
    """

    # Insert CSS before </head> and script before </body>
    head_injected = False
    body_injected = False
    lower_html = html.lower()
    # Inject CSS before closing head (case-insensitive)
    head_idx = lower_html.rfind('</head>')
    if head_idx != -1:
        html = html[:head_idx] + f'<style>{css}</style>' + html[head_idx:]
        head_injected = True
    else:
        html = f'<!-- no </head>; prepended CSS -->\n<style>{css}</style>' + html
    # Inject script before closing body (fallback to before </html>)
    lower_html = html.lower()
    body_idx = lower_html.rfind('</body>')
    if body_idx != -1:
        html = html[:body_idx] + script + guide_script + html[body_idx:]
        body_injected = True
    else:
        html_lower2 = html.lower()
        html_idx = html_lower2.rfind('</html>')
        if html_idx != -1:
            html = html[:html_idx] + script + guide_script + html[html_idx:]
        else:
            html = html + script + guide_script + '\n<!-- no </body> or </html>; appended script -->'
    print(f"[map-embed] Injected CSS into head: {head_injected}; Injected script into body: {body_injected}")

    response = HttpResponse(html)
    # Avoid COOP warnings on non-HTTPS dev origins
    response['Cross-Origin-Opener-Policy'] = 'unsafe-none'
    response['X-Map-Embed'] = 'ok'
    response['X-Map-Embed-Template'] = str(tname)
    response['X-Map-Embed-Injected'] = f"head={head_injected},body={body_injected}"
    print(f"[map-embed] Returning response length: {len(html)} bytes")
    return response


def listing_map_data(request, listing_id: int):
    """Return the DATA object from the pre-generated map HTML as JSON.

    Allows embedding the map directly in the property details page without an iframe
    while still reusing the same precomputed amenities distances from the exported files.
    """
    from django.template.loader import select_template
    print(f"[map-data] Incoming request: listing_id={listing_id}")
    try:
        template = select_template([
            f'newfrontend/maps/listing_{listing_id}.html',
            f'newfrontend/maps/listing_{listing_id}_map_only.html',
        ])
    except Exception:
        print(f"[map-data] No template found for listing_id={listing_id}")
        return JsonResponse({"error": "map not found"}, status=404)

    html = template.render({}, request)
    print(f"[map-data] Rendered HTML length: {len(html)} bytes")

    # Extract JS const DATA = {...}; using a tolerant regex
    m = re.search(r"const\\s+DATA\\s*=\\s*(\{[\\s\\S]*?\})\\s*;", html)
    if not m:
        print("[map-data] DATA object not found in HTML")
        return JsonResponse({"error": "data not found"}, status=500)

    data_str = m.group(1)
    try:
        data = json.loads(data_str)
    except Exception as e:
        print(f"[map-data] Failed to parse DATA JSON: {e}")
        # As a fallback, attempt to fix trailing commas etc. (minimal)
        try:
            data = json.loads(data_str.replace("\n", " "))
        except Exception:
            return JsonResponse({"error": "invalid data"}, status=500)

    return JsonResponse(data)
