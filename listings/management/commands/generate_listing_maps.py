import json
import os
import re
import hashlib
import zipfile
import urllib.request
from urllib.error import HTTPError, URLError
from datetime import datetime, timezone

from django.core.management.base import BaseCommand
from django.conf import settings

from listings.models import Listing

EXTERNAL_AMENITIES_BASE = 'http://100.89.48.48:8006/map/amenities/'

TEMPLATES_DIR = None
CONTEXTS_DIR = None
MAPS_DIR = None

KEY_MAP = {
    'metro': 'closest_stations',
    'metrobus': 'closest_metrobus',
    'bus': 'closest_bus_stops',
    'grocery': 'closest_grocery_stores',
    'clothing': 'closest_clothing_stores',
    'malls': 'malls',
    'parks': 'parks',
    'taxi': 'taxi',
    'minibus': 'minibus',
    'bicycle': 'bicycle',
}

CONTEXT_KEY_MAP = {
    'metro': 'metro',
    'metrobus': 'metrobus',
    'bus': 'bus',
    'grocery': 'grocery',
    'clothing': 'clothing',
    'malls': 'malls',
    'parks': 'parks',
    'taxi': 'taxi',
    'minibus': 'minibus',
    'bicycle': 'bicycle',
}


def _init_dirs():
    global TEMPLATES_DIR, CONTEXTS_DIR, MAPS_DIR
    base = settings.BASE_DIR
    TEMPLATES_DIR = os.path.join(base, 'templates', 'newfrontend', 'maps')
    CONTEXTS_DIR = os.path.join(base, 'templates', 'newfrontend', 'mapstandalone', 'contexts')
    MAPS_DIR = os.path.join(base, 'maps')
    for d in [TEMPLATES_DIR, CONTEXTS_DIR, MAPS_DIR]:
        os.makedirs(d, exist_ok=True)


def rewrite_tile_layer(html):
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
    html = re.sub(
        r"(L\.tileLayer\([^,]+,\s*\{)([\s\S]*?)(\}\))",
        lambda m: m.group(1) + "\n            referrerPolicy: 'no-referrer-when-downgrade'," + m.group(2) + m.group(3),
        html,
        count=1
    )
    return html


def fetch_external_html(listing):
    if listing.latitude is None or listing.longitude is None:
        return None
    url = f"{EXTERNAL_AMENITIES_BASE}?q={listing.latitude},{listing.longitude}"
    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': 'CoralCity/1.0',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        })
        with urllib.request.urlopen(req, timeout=30) as resp:
            if resp.status != 200:
                return None
            content_type = resp.headers.get('Content-Type', '')
            if 'text/html' not in content_type.lower():
                return None
            charset = resp.headers.get_content_charset('utf-8')
            html = resp.read().decode(charset, errors='replace')
            return rewrite_tile_layer(html)
    except (HTTPError, URLError, TimeoutError, ValueError) as e:
        print(f"    [WARN] Failed to fetch amenities: {e}")
        return None


def parse_amenities_from_html(html):
    m = re.search(r'(?:const|var|let)\s+amenities\s*=\s*(\{[\s\S]*?\});', html)
    if not m:
        return None
    data_str = m.group(1)
    try:
        return json.loads(data_str)
    except json.JSONDecodeError:
        try:
            data_str_clean = re.sub(r',(\s*[}\]])', r'\1', data_str)
            return json.loads(data_str_clean)
        except json.JSONDecodeError:
            return None


def convert_coords_to_geojson(items):
    result = []
    for item in items:
        if 'lat' in item and 'lng' in item and item['lat'] is not None and item['lng'] is not None:
            entry = {
                'id': item.get('id'),
                'name': item.get('name'),
                'distance_m': item.get('distance_m'),
                'location': {
                    'type': 'Point',
                    'coordinates': [item['lng'], item['lat']],
                },
            }
        else:
            entry = {
                'id': item.get('id'),
                'name': item.get('name'),
                'distance_m': item.get('distance_m'),
                'location': None,
            }
        if 'geometry' in item and item['geometry'] is not None:
            entry['geometry'] = item['geometry']
        result.append(entry)
    return result


def build_data_object(listing, amenities):
    data = {
        'listing': {
            'id': str(listing.pk),
            'title': listing.title,
            'price': listing.price,
            'lat': listing.latitude,
            'lng': listing.longitude,
        },
    }
    for external_key, internal_key in KEY_MAP.items():
        raw_items = amenities.get(external_key, [])
        if isinstance(raw_items, list):
            data[internal_key] = convert_coords_to_geojson(raw_items)
        else:
            data[internal_key] = []
    return data


def build_context_data(listing, amenities):
    ctx = {
        'listing': {
            'id': str(listing.pk),
            'title': listing.title,
            'lat': listing.latitude,
            'lng': listing.longitude,
        },
    }
    for external_key, context_key in CONTEXT_KEY_MAP.items():
        raw_items = amenities.get(external_key, [])
        if isinstance(raw_items, list):
            ctx[context_key] = convert_coords_to_geojson(raw_items)
        else:
            ctx[context_key] = []
    return ctx


def inject_data_into_html(html, data):
    data_block = '\n<script>\nconst DATA = ' + json.dumps(data, ensure_ascii=False, indent=2) + ';\n</script>\n'
    body_match = list(re.finditer('</body>', html, re.IGNORECASE))
    if body_match:
        idx = body_match[-1].start()
        return html[:idx] + data_block + html[idx:]
    html_match = list(re.finditer('</html>', html, re.IGNORECASE))
    if html_match:
        idx = html_match[-1].start()
        return html[:idx] + data_block + html[idx:]
    return html + data_block


def extract_body_content(html):
    """Extract the inner content of <html> (strips <html>, <head>, <body> wrappers
    but keeps style/script/link tags that were in <head> for standalone map rendering)."""
    low = html.lower()

    html_start = low.find('<html')
    html_end = low.rfind('</html>')

    if html_start == -1 or html_end == -1:
        return html

    inner = html[html_start:html_end]

    # Keep <style>, <link>, and <script> blocks (from head or body)
    # Remove <head>, </head>, <body>, </body>, <html>, </html> tags
    inner = re.sub(r'</?head[^>]*>', '', inner, flags=re.IGNORECASE)
    inner = re.sub(r'</?body[^>]*>', '', inner, flags=re.IGNORECASE)
    inner = re.sub(r'</?html[^>]*>', '', inner, flags=re.IGNORECASE)
    inner = re.sub(r'<!DOCTYPE[^>]*>', '', inner, flags=re.IGNORECASE)

    return inner.strip()


def save_file(path, content):
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)


def sha256_file(content):
    return hashlib.sha256(content.encode('utf-8')).hexdigest()


def update_aggregated_contexts(all_contexts):
    manifest = {
        'count': len(all_contexts),
        'directory': 'distill_out/simplified/contexts',
        'items': [],
    }
    for listing_id, ctx_data, ctx_content in all_contexts:
        manifest['items'].append({
            'file': f'listing_{listing_id}_context.json',
            'listing_id': str(listing_id),
            'title': ctx_data['listing']['title'],
            'bytes': len(ctx_content.encode('utf-8')),
            'mtime': int(datetime.now(timezone.utc).timestamp()),
            'sha256': sha256_file(ctx_content),
        })

    agg_path = os.path.join(CONTEXTS_DIR, 'contexts.json')
    agg_content = json.dumps([c[1] for c in all_contexts], ensure_ascii=False, indent=2)
    save_file(agg_path, agg_content)

    manifest_path = os.path.join(CONTEXTS_DIR, 'contexts_manifest.json')
    manifest_content = json.dumps(manifest, ensure_ascii=False, indent=2)
    save_file(manifest_path, manifest_content)

    zip_path = os.path.join(CONTEXTS_DIR, 'contexts_export.zip')
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for listing_id, _, ctx_content in all_contexts:
            zf.writestr(f'listing_{listing_id}_context.json', ctx_content.encode('utf-8'))

    print(f"  Updated aggregated: contexts.json ({len(all_contexts)} items), manifest, zip ({zip_path})")


class Command(BaseCommand):
    help = 'Fetch external amenity maps and save as standalone HTML templates for each listing'

    def add_arguments(self, parser):
        parser.add_argument('--listing-id', type=str, help='Generate for a specific listing ID only')
        parser.add_argument('--force', action='store_true', help='Regenerate even if file exists')

    def handle(self, *args, **options):
        _init_dirs()
        listing_id = options.get('listing_id')
        force = options.get('force', False)

        if listing_id:
            listings = Listing.objects.filter(pk=listing_id)
            if not listings.exists():
                self.stderr.write(f"Listing with ID '{listing_id}' not found")
                return
        else:
            listings = Listing.objects.filter(
                is_published=True,
                latitude__isnull=False,
                longitude__isnull=False,
            ).order_by('pk')

        total = listings.count()
        self.stdout.write(f"Processing {total} listing(s)...")

        all_contexts = []
        success = 0
        skipped = 0
        failed = 0

        for listing in listings:
            lid = listing.pk
            self.stdout.write(f"  [{lid}] {listing.title[:50]}...")

            map_only_path = os.path.join(TEMPLATES_DIR, f'listing_{lid}_map_only.html')
            full_map_path = os.path.join(TEMPLATES_DIR, f'listing_{lid}.html')
            context_path = os.path.join(CONTEXTS_DIR, f'listing_{lid}_context.json')
            maps_dir_path = os.path.join(MAPS_DIR, f'listing_{lid}_map_only.html')

            existing_paths = [map_only_path, full_map_path, context_path]
            if all(os.path.exists(p) for p in existing_paths) and not force:
                self.stdout.write(f"    [SKIP] All files exist (use --force to regenerate)")
                ctx_data = json.load(open(context_path, 'r', encoding='utf-8'))
                ctx_content = open(context_path, 'r', encoding='utf-8').read()
                all_contexts.append((lid, ctx_data, ctx_content))
                skipped += 1
                continue

            external_html = fetch_external_html(listing)
            if not external_html:
                self.stderr.write(f"    [FAIL] Could not fetch from external service")
                failed += 1
                continue

            amenities = parse_amenities_from_html(external_html)
            if not amenities:
                self.stderr.write(f"    [FAIL] Could not parse amenities data from response")
                failed += 1
                continue

            data_obj = build_data_object(listing, amenities)
            html_with_data = inject_data_into_html(external_html, data_obj)

            save_file(full_map_path, html_with_data)
            save_file(map_only_path, extract_body_content(html_with_data))
            save_file(maps_dir_path, extract_body_content(html_with_data))
            self.stdout.write(f"    [OK] Saved external map -> listing_{lid}.html + _map_only.html ({len(html_with_data)} bytes)")

            ctx_data = build_context_data(listing, amenities)
            ctx_content = json.dumps(ctx_data, ensure_ascii=False, indent=2)
            save_file(context_path, ctx_content)
            self.stdout.write(f"    [OK] Saved context JSON -> listing_{lid}_context.json")

            all_contexts.append((lid, ctx_data, ctx_content))
            success += 1

        if all_contexts:
            update_aggregated_contexts(all_contexts)

        self.stdout.write(f"\nDone: {success} generated, {skipped} skipped, {failed} failed (of {total} total)")
