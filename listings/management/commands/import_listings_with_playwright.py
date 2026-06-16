import csv
import re
import time
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction, connection

from listings.models import Listing
from listings.models import ListingImage
from django.core.files.base import ContentFile
import requests
from realtors.models import Realtor
import threading
from django.db import close_old_connections


def clean_int_from_text(text: str) -> int:
    if not text:
        return 0
    digits = re.findall(r"\d+", str(text))
    if not digits:
        return 0
    try:
        return int("".join(digits))
    except ValueError:
        return 0


def parse_bedrooms_from_oda_sayisi(value: str) -> int:
    if not value:
        return 0
    m = re.match(r"\s*(\d+)\s*\+", value)
    if m:
        return int(m.group(1))
    return clean_int_from_text(value)


MONTHS_TR = {
    "ocak": 1,
    "şubat": 2,
    "subat": 2,
    "mart": 3,
    "nisan": 4,
    "mayıs": 5,
    "mayis": 5,
    "haziran": 6,
    "temmuz": 7,
    "ağustos": 8,
    "agustos": 8,
    "eylül": 9,
    "eylul": 9,
    "ekim": 10,
    "kasım": 11,
    "kasim": 11,
    "aralık": 12,
    "aralik": 12,
}


def parse_tr_date(value: str) -> datetime | None:
    if not value:
        return None
    parts = str(value).strip().split()
    if len(parts) >= 3:
        try:
            day = int(re.sub(r"\D", "", parts[0]))
        except ValueError:
            return None
        month_name = parts[1].lower()
        month = MONTHS_TR.get(month_name)
        if not month:
            return None
        try:
            year = int(re.sub(r"\D", "", parts[2]))
        except ValueError:
            return None
        try:
            return datetime(year, month, day)
        except ValueError:
            return None
    return None


def parse_deal_and_type(value: str) -> tuple[str | None, str]:
    if not value:
        return None, ""
    v_low = value.strip().lower()
    deal = None
    if "kiralık" in v_low or "kiralik" in v_low:
        deal = "kiralik"
    elif "satılık" in v_low or "satilik" in v_low:
        deal = "satis"
    parts = value.strip().split()
    real_type = value.strip()
    if len(parts) >= 2:
        real_type = " ".join(parts[1:])
    return deal, real_type


def extract_lat_lon_from_url(url: str) -> tuple[float | None, float | None]:
    if not url:
        return None, None
    m = re.search(r"/(-?\d+\.\d+),(-?\d+\.\d+)", url)
    if m:
        try:
            return float(m.group(1)), float(m.group(2))
        except ValueError:
            return None, None
    m = re.search(r"[?&](?:q|ll)=(-?\d+\.\d+),(-?\d+\.\d+)", url)
    if m:
        try:
            return float(m.group(1)), float(m.group(2))
        except ValueError:
            return None, None
    return None, None


def parse_location_from_breadcrumb_texts(texts: list[str]):
    texts = [t for t in texts if t]
    if len(texts) >= 3:
        return texts[0], texts[1], texts[-1]
    return None, None, None


def parse_bool_text(value: str) -> bool | None:
    if value is None:
        return None
    s = value.strip().lower()
    if s in {"evet", "var", "yes", "available"}:
        return True
    if s in {"hayır", "hayir", "yok", "no", "not available"}:
        return False
    return None


class Command(BaseCommand):
    help = "Import listings using Playwright to load pages and extract fields. Reads URLs from a CSV."

    def add_arguments(self, parser):
        parser.add_argument(
            "csv_path",
            nargs="?",
            default="listings/links.csv",
            help="Path to CSV (one URL per line, or header with 'url')",
        )
        parser.add_argument("--realtor-id", type=int, required=True, help="Realtor ID")
        parser.add_argument("--delay", type=float, default=1.5, help="Seconds to wait between URLs")
        parser.add_argument("--timeout", type=int, default=20000, help="Per-action timeout in ms")
        parser.add_argument("--headless", action="store_true", help="Run headless (default)")
        parser.add_argument("--headed", action="store_true", help="Run with browser UI (overrides --headless)")
        parser.add_argument("--storage-state", type=str, default="", help="Path to Playwright storage state JSON for authenticated session")
        parser.add_argument("--save-html-dir", type=str, default="", help="If set, saves page HTML for each URL")
        parser.add_argument("--debug", action="store_true", help="Verbose step-by-step logs")
        parser.add_argument("--dry-run", action="store_true", help="Parse only; do not save to DB")
        parser.add_argument("--retries", type=int, default=2, help="Retries per URL when blocked or placeholder page is detected")
        parser.add_argument("--cooldown", type=float, default=5.0, help="Seconds to sleep before retrying a blocked page")
        parser.add_argument("--skip-geocode", action="store_true", help="Do not geocode during save; leave coordinates missing")
        parser.add_argument("--defer-geocode", action="store_true", help="Alias of --skip-geocode; geocode later via geocode_missing_listings command")
        parser.add_argument("--default-city", type=str, default="", help="Fallback city if breadcrumb missing")
        parser.add_argument("--default-state", type=str, default="", help="Fallback district if breadcrumb missing")
        parser.add_argument("--default-zipcode", type=str, default="", help="Fallback zipcode")
        parser.add_argument("--default-address", type=str, default="", help="Fallback address")
        parser.add_argument("--cookie-string", type=str, default="", help="Cookie header string from your browser (e.g. 'sid=...; other=...')")
        parser.add_argument("--cookie-file", type=str, default="", help="Path to cookies.txt (Netscape format) exported from browser")
        parser.add_argument("--cookie-domain", type=str, default=".sahibinden.com", help="Domain to attach cookies to (default .sahibinden.com)")
        parser.add_argument(
            "--header",
            action="append",
            default=[],
            help="Additional request header 'Name: Value'. Repeat for multiple headers.",
        )
        parser.add_argument("--no-images", action="store_true", help="Do not download/attach listing images")
        parser.add_argument("--images-max", type=int, default=15, help="Maximum number of images to import per listing")

    def read_urls(self, path: Path) -> list[str]:
        text = path.read_text(encoding="utf-8", errors="ignore")
        try:
            rows = list(csv.DictReader(text.splitlines()))
            if rows and "url" in rows[0]:
                urls = [r.get("url", "").strip() for r in rows]
                return [u for u in urls if u and not u.startswith("#")]
        except Exception:
            pass
        urls: list[str] = []
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            first = line.split(",")[0].strip()
            if first:
                urls.append(first)
        return urls

    def handle(self, *args, **options):
        try:
            from playwright.sync_api import sync_playwright
        except Exception as e:
            raise CommandError(
                "Playwright is required. Add 'playwright' to requirements and run 'python -m playwright install chromium'"
            ) from e

        csv_path = Path(options["csv_path"])
        realtor_id = options["realtor_id"]
        delay = float(options["delay"]) or 0.0
        timeout = int(options["timeout"]) or 20000
        headless = not options.get("headed")
        storage_state = options.get("storage_state") or ""
        save_dir = Path(options.get("save_html_dir") or "") if options.get("save_html_dir") else None
        debug = bool(options.get("debug"))
        dry_run = bool(options.get("dry_run"))
        retries = int(options.get("retries") or 0)
        cooldown = float(options.get("cooldown") or 0.0)
        skip_geocode = bool(options.get("skip_geocode")) or bool(options.get("defer_geocode"))
        default_city = options.get("default_city") or ""
        default_state = options.get("default_state") or ""
        default_zipcode = options.get("default_zipcode") or ""
        default_address = options.get("default_address") or ""
        cookie_string = options.get("cookie_string") or ""
        cookie_file = options.get("cookie_file") or ""
        cookie_domain = options.get("cookie_domain") or ".sahibinden.com"
        header_kvs: list[str] = options.get("header") or []
        no_images = bool(options.get("no_images"))
        images_max = int(options.get("images_max") or 0) or 15

        def dbg(msg: str):
            if debug:
                ts = datetime.now().strftime("%H:%M:%S")
                self.stdout.write(f"[{ts}] {msg}")

        if not csv_path.exists():
            raise CommandError(f"CSV not found: {csv_path}")
        realtor = Realtor.objects.filter(id=realtor_id).first()
        if not realtor:
            raise CommandError(f"Realtor not found with id={realtor_id}")

        urls = self.read_urls(csv_path)
        if not urls:
            self.stdout.write(self.style.WARNING("No URLs found in CSV"))
            return

        created = 0
        skipped = 0
        updated = 0

        # Default headers (applied to every request). User-specified headers override these.
        default_headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Referer": "https://www.sahibinden.com/",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }

        # Parse extra headers from CLI
        extra_headers = {}
        for kv in header_kvs:
            if not isinstance(kv, str) or ":" not in kv:
                continue
            name, val = kv.split(":", 1)
            extra_headers[name.strip()] = val.strip()
        if extra_headers:
            dbg(f"Extra headers provided: {list(extra_headers.keys())}")
        # Merge defaults with user headers (user overrides)
        merged_headers = {**default_headers, **extra_headers}

        # Parse cookie string and/or cookies.txt into cookies
        cookies = []
        if cookie_string:
            try:
                for part in cookie_string.split(";"):
                    if not part.strip():
                        continue
                    if "=" not in part:
                        continue
                    name, value = part.split("=", 1)
                    cookies.append({
                        "name": name.strip(),
                        "value": value.strip(),
                        "domain": cookie_domain,
                        "path": "/",
                    })
                dbg(f"Parsed {len(cookies)} cookies from cookie-string: {[c['name'] for c in cookies]}")
            except Exception as e:
                dbg(f"Failed to parse cookie string: {e}")

        # Netscape cookies.txt support
        if not cookie_file:
            # Auto-detect a default cookies file in listings/ if present
            auto_path = Path("listings/5dba612c-7239-43f0-9a4c-285062377c6f.txt")
            if auto_path.exists():
                cookie_file = str(auto_path)
        if cookie_file:
            try:
                p = Path(cookie_file)
                if not p.exists():
                    raise FileNotFoundError(cookie_file)
                lines = p.read_text(encoding="utf-8", errors="ignore").splitlines()
                added = 0
                for line in lines:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    parts = line.split("\t")
                    if len(parts) != 7:
                        continue
                    domain, flag, path, secure, expires, name, value = parts
                    cookie_dict = {
                        "name": name,
                        "value": value,
                        "domain": domain,
                        "path": path or "/",
                        "secure": (secure.upper() == "TRUE"),
                    }
                    try:
                        exp = int(expires)
                        if exp > 0:
                            cookie_dict["expires"] = exp
                    except Exception:
                        pass
                    cookies.append(cookie_dict)
                    added += 1
                dbg(f"Loaded {added} cookies from cookies.txt: {cookie_file}")
            except Exception as e:
                dbg(f"Failed to read cookies.txt: {e}")

        with sync_playwright() as p:
            dbg("Launching Chromium")
            browser = p.chromium.launch(headless=headless)
            ctx_kwargs = {
                "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
                "viewport": {"width": 1366, "height": 900},
                "locale": "tr-TR",
            }
            if storage_state:
                ctx_kwargs["storage_state"] = storage_state
                dbg(f"Using storage state: {storage_state}")
            # Always apply merged default+user headers
            ctx_kwargs["extra_http_headers"] = merged_headers
            dbg("Applied default+extra HTTP headers to context")
            context = browser.new_context(**ctx_kwargs)
            if cookies:
                try:
                    context.add_cookies(cookies)
                    dbg("Session cookies added to context")
                except Exception as e:
                    dbg(f"Failed to add cookies: {e}")

            # Helper to run ORM lookups safely outside async context
            def find_existing(external_id_value: str | None, original_url_value: str | None):
                result = {"obj": None}

                def _lookup():
                    try:
                        close_old_connections()
                        obj = None
                        if external_id_value:
                            obj = Listing.objects.filter(external_id=external_id_value).first()
                        if obj is None and original_url_value:
                            obj = Listing.objects.filter(original_url=original_url_value).first()
                        result["obj"] = obj
                    finally:
                        close_old_connections()

                t = threading.Thread(target=_lookup, name="listing-lookup-thread", daemon=True)
                t.start()
                t.join()
                return result["obj"]

            for idx, url in enumerate(urls, start=1):
                dbg(f"[{idx}/{len(urls)}] Goto: {url}")
                page = context.new_page()
                page.set_default_timeout(timeout)
                try:
                    page.goto(url, wait_until="domcontentloaded")
                except Exception as e:
                    self.stdout.write(self.style.WARNING(f"[{idx}] Navigation failed: {e} -> {url}"))
                    skipped += 1
                    continue

                # Optional page HTML save
                if save_dir:
                    try:
                        save_dir.mkdir(parents=True, exist_ok=True)
                        safe_name = re.sub(r"[^a-zA-Z0-9_-]", "_", url)[:180] + ".html"
                        content = page.content()
                        (save_dir / safe_name).write_text(content, encoding="utf-8")
                        dbg(f"Saved HTML to: {(save_dir / safe_name)}")
                    except Exception as e:
                        dbg(f"Failed to save HTML: {e}")

                # Allow dynamic content to render
                try:
                    page.wait_for_selector("div.classifiedDetailTitle >> h1", timeout=timeout)
                except Exception:
                    dbg("Title selector not found within timeout; proceeding with current DOM")

                # Extract title with short, non-blocking calls
                def quick_text(sel: str, ms: int = 1500) -> str:
                    try:
                        t = page.locator(sel).first.text_content(timeout=ms)
                        return (t or "").strip()
                    except Exception:
                        return ""

                title = quick_text("div.classifiedDetailTitle > h1") or quick_text("h1")
                if not title:
                    try:
                        title = (page.title() or "").strip()
                    except Exception:
                        title = ""
                dbg(f"Title: {title!r}")

                # Price
                price_text = ""
                try:
                    price_text = page.locator("div.classifiedInfo .classified-price-wrapper").first.inner_text().strip()
                except Exception:
                    price_text = ""
                price = clean_int_from_text(price_text)
                dbg(f"Price raw: {price_text!r} -> {price}")

                # Details list
                details: dict[str, str] = {}
                try:
                    lis = page.locator("ul.classifiedInfoList > li")
                    for i in range(lis.count()):
                        li = lis.nth(i)
                        try:
                            key = li.locator("strong").first.inner_text().strip()
                            val = li.locator("span").first.inner_text().strip()
                        except Exception:
                            continue
                        if key:
                            details[key] = val
                            dbg(f"Detail: {key!r} -> {val!r}")
                except Exception:
                    pass

                property_type_raw = details.get("Emlak Tipi", "")
                deal_type, property_type = parse_deal_and_type(property_type_raw)
                bedrooms = (details.get("Oda Sayısı", "") or details.get("Oda Sayisi", "")).strip()
                bathrooms = clean_int_from_text(details.get("Banyo Sayısı", "") or details.get("Banyo Sayisi", ""))
                m2_brut_text = details.get("m² (Brüt)", "") or details.get("m2 (Brut)", "")
                try:
                    m2_brut = int(re.sub(r"\D", "", m2_brut_text)) if m2_brut_text else 0
                except ValueError:
                    m2_brut = 0
                sqft = int(round(m2_brut * 10.7639)) if m2_brut else 0
                list_date = parse_tr_date(details.get("İlan Tarihi", "") or details.get("Ilan Tarihi", ""))
                ad_date = list_date
                external_id = (details.get("İlan No") or details.get("Ilan No") or "").strip()
                dbg(f"Type: {property_type_raw!r}->{property_type!r}; Beds: {bedrooms}; Baths: {bathrooms}; m2={m2_brut} sqft={sqft}; date={list_date}")

                # Bail early if page likely blocked/placeholder, with lightweight retries
                if not external_id or not title or title.lower() == "www.sahibinden.com":
                    blocked = True
                    attempts = 0
                    while blocked and attempts < retries:
                        attempts += 1
                        self.stdout.write(self.style.WARNING(f"[{idx}] Blocked/invalid page; retry {attempts}/{retries} after {cooldown:.1f}s"))
                        if cooldown > 0:
                            time.sleep(cooldown)
                        try:
                            page.reload(wait_until="domcontentloaded")
                        except Exception:
                            break
                        # Re-extract title and external_id quickly
                        def quick_text(sel: str, ms: int = 1500) -> str:
                            try:
                                t = page.locator(sel).first.text_content(timeout=ms)
                                return (t or "").strip()
                            except Exception:
                                return ""
                        title = quick_text("div.classifiedDetailTitle > h1") or quick_text("h1")
                        if not title:
                            try:
                                title = (page.title() or "").strip()
                            except Exception:
                                title = ""
                        details = {}
                        try:
                            lis = page.locator("ul.classifiedInfoList > li")
                            for i in range(lis.count()):
                                li = lis.nth(i)
                                try:
                                    key = li.locator("strong").first.inner_text().strip()
                                    val = li.locator("span").first.inner_text().strip()
                                except Exception:
                                    continue
                                if key:
                                    details[key] = val
                        except Exception:
                            pass
                        external_id = (details.get("İlan No") or details.get("Ilan No") or "").strip()
                        blocked = (not external_id) or (not title) or (title.strip().lower() == "www.sahibinden.com")
                    if blocked:
                        self.stdout.write(self.style.WARNING(f"[{idx}] SKIP: missing/invalid listing markers after retries."))
                        try:
                            page.close()
                        except Exception:
                            pass
                        skipped += 1
                        if delay > 0:
                            time.sleep(delay)
                        continue

                # Check if this listing already exists (by external_id or original_url)
                existing_listing = None
                lookup_source = None
                try:
                    existing_listing = find_existing(external_id, url)
                    if existing_listing:
                        if existing_listing.external_id:
                            lookup_source = f"external_id={existing_listing.external_id}"
                        elif existing_listing.original_url:
                            lookup_source = "original_url"
                except Exception as e:
                    dbg(f"Existing lookup failed: {e}")

                # Map link
                lat = lon = None
                try:
                    href = page.locator("div.getDirectionsButton > a").first.get_attribute("href")
                    if href:
                        lat, lon = extract_lat_lon_from_url(href)
                        dbg(f"Map href: {href} -> lat={lat}, lon={lon}")
                except Exception:
                    pass

                # Breadcrumbs for location
                city_b = district_b = neighborhood_b = None
                try:
                    a_nodes = page.locator("a[data-click-label^='Adres Breadcrumb']")
                    texts = []
                    for i in range(a_nodes.count()):
                        t = a_nodes.nth(i).inner_text().strip()
                        if t:
                            texts.append(t)
                    city_b, district_b, neighborhood_b = parse_location_from_breadcrumb_texts(texts)
                except Exception:
                    pass
                dbg(f"Breadcrumbs -> city={city_b!r}, district={district_b!r}, neighborhood={neighborhood_b!r}")

                address = neighborhood_b or default_address
                city = city_b or default_city
                state = district_b or default_state
                zipcode = default_zipcode

                # Extra details and attributes
                extra_keys = [
                    "Bina Yaşı",
                    "Bulunduğu Kat",
                    "Kat Sayısı",
                    "Isıtma",
                    "Balkon",
                    "Eşyalı",
                    "Aidat",
                ]
                building_age = clean_int_from_text(details.get("Bina Yaşı", "") or details.get("Bina Yasi", "")) or None
                floor_number = clean_int_from_text(details.get("Bulunduğu Kat", "") or details.get("Bulundugu Kat", "")) or None
                floors_total = clean_int_from_text(details.get("Kat Sayısı", "") or details.get("Kat Sayisi", "")) or None
                heating = (details.get("Isıtma") or details.get("Isitma") or "").strip()
                kitchen_type = (details.get("Mutfak") or details.get("Mutfak Tipi") or "").strip()
                balcony_text = (details.get("Balkon") or "").strip()
                balcony = balcony_text
                elevator = parse_bool_text(details.get("Asansör"))
                parking_area = (details.get("Otopark") or "").strip()
                furnished = parse_bool_text(details.get("Eşyalı") or details.get("Esyȧli"))
                usage_status = (details.get("Kullanım Durumu") or details.get("Kullanim Durumu") or "").strip()
                in_complex = parse_bool_text(details.get("Site İçerisinde") or details.get("Site Icerisinde"))
                complex_name = (details.get("Site Adı") or details.get("Site Adi") or "").strip()
                maintenance_fee = clean_int_from_text(details.get("Aidat", "")) or None
                deposit = clean_int_from_text(details.get("Depozito", "") or details.get("Depozito (TL)", "")) or None
                deed_status = (details.get("Tapu Durumu") or "").strip()
                from_whom = (details.get("Kimden") or "").strip()

                description_parts = []
                for k in extra_keys:
                    v = details.get(k)
                    if v:
                        description_parts.append(f"{k}: {v}")
                description = " | ".join(description_parts)

                dbg("Constructing Listing model instance or updating existing")
                if existing_listing:
                    listing = existing_listing
                    # Minimal non-destructive updates
                    if not listing.original_url:
                        listing.original_url = url
                    if (listing.latitude is None or listing.longitude is None) and (lat is not None and lon is not None):
                        listing.latitude = lat
                        listing.longitude = lon
                    # Optionally update price or other fields only if missing; avoid overwriting user's edits
                    if not listing.description and description:
                        listing.description = description
                    if not listing.property_type and property_type:
                        listing.property_type = property_type
                    if not listing.deal_type and deal_type:
                        listing.deal_type = deal_type
                else:
                    listing = Listing(
                        realtor=realtor,
                        title=title,
                        address=address,
                        city=city,
                        state=state,
                        zipcode=zipcode,
                        description=description,
                        price=price,
                        bedrooms=bedrooms,
                        deal_type=deal_type or "satis",
                        property_type=property_type,
                        bathrooms=bathrooms,
                        sqft=sqft,
                        lot_size=Decimal("0.0"),
                        external_id=external_id,
                        ad_date=list_date.date() if isinstance(list_date, datetime) else list_date,
                        m2_gross=m2_brut or None,
                        m2_net=clean_int_from_text(details.get("m² (Net)", "") or details.get("m2 (Net)", "")) or None,
                        rooms_text=(details.get("Oda Sayısı", "") or details.get("Oda Sayisi", "")).strip(),
                        building_age=building_age,
                        floor_number=floor_number,
                        floors_total=floors_total,
                        heating=heating,
                        kitchen_type=kitchen_type,
                        balcony=balcony,
                        elevator=elevator,
                        parking_area=parking_area,
                        furnished=furnished,
                        usage_status=usage_status,
                        in_complex=in_complex,
                        complex_name=complex_name,
                        maintenance_fee=maintenance_fee,
                        deposit=deposit,
                        deed_status=deed_status,
                        from_whom=from_whom,
                        original_url=url,
                    )
                    if lat is not None and lon is not None:
                        listing.latitude = lat
                        listing.longitude = lon
                    if list_date:
                        listing.list_date = list_date

                # Collect image URLs from within .classifiedDetailPhotos (all pictures)
                # - Consider both <img> (src or data-src) and <source> (srcset)
                # - Prefer non-AVIF URLs; if AVIF, attempt .jpg fallback as site supports both
                image_urls: list[str] = []
                skip_image_download = False
                if not no_images:
                    # Fast pre-check: if existing listing already has valid images, skip collection and downloads
                    if existing_listing:
                        try:
                            imgs = list(listing.images.all())
                            if imgs:
                                all_ok = True
                                for im in imgs:
                                    f = getattr(im, 'image', None)
                                    name = getattr(f, 'name', None) if f else None
                                    if not f or not name:
                                        all_ok = False
                                        break
                                    try:
                                        if not f.storage.exists(name):
                                            all_ok = False
                                            break
                                    except Exception:
                                        all_ok = False
                                        break
                                if all_ok:
                                    skip_image_download = True
                                    dbg("Existing listing images are valid; skipping image collection and download")
                        except Exception:
                            pass

                    try:
                        if skip_image_download:
                            raise Exception("skip-image-collection")
                        seen: set[str] = set()
                        container = page.locator("div.classifiedDetailPhotos")

                        # Helper to normalize a single URL (prefer JPG if AVIF)
                        def normalize_url(u: str) -> str:
                            u = (u or "").strip()
                            if not u:
                                return ""
                            # If srcset provides descriptors (e.g., "... 1x"), take just the URL
                            first_part = u.split()[0]
                            # Convert .avif to .jpg (server provides jpg fallback)
                            return re.sub(r"\.avif(?:\?.*)?$", ".jpg", first_part)

                        # 1) <img> elements (prefer data-src when present)
                        try:
                            imgs = container.locator("img") if container.count() else page.locator(".classifiedDetailPhotos img")
                            for i in range(imgs.count()):
                                node = imgs.nth(i)
                                cand = node.get_attribute("data-src") or node.get_attribute("src")
                                if not cand:
                                    continue
                                cand = normalize_url(cand)
                                if not cand:
                                    continue
                                # Skip placeholders and non-http
                                if cand.startswith("data:") or "blank" in cand or not cand.startswith("http"):
                                    continue
                                if cand not in seen:
                                    seen.add(cand)
                                    image_urls.append(cand)
                        except Exception:
                            pass

                        # 2) <source> elements (any type, parse srcset)
                        try:
                            sources = container.locator("source") if container.count() else page.locator(".classifiedDetailPhotos source")
                            for i in range(sources.count()):
                                srcset = sources.nth(i).get_attribute("srcset")
                                if not srcset:
                                    continue
                                # srcset may contain multiple entries separated by commas
                                for part in srcset.split(','):
                                    cand = normalize_url(part)
                                    if not cand:
                                        continue
                                    if cand.startswith("data:") or "blank" in cand or not cand.startswith("http"):
                                        continue
                                    if cand not in seen:
                                        seen.add(cand)
                                        image_urls.append(cand)
                        except Exception:
                            pass

                        # Respect max images
                        if images_max > 0:
                            image_urls = image_urls[:images_max]
                        dbg(f"Found {len(image_urls)} image candidates inside .classifiedDetailPhotos")
                    except Exception as e:
                        if str(e) == "skip-image-collection":
                            pass
                        else:
                            dbg(f"Image extraction failed: {e}")

                # Pre-download image bytes so DB writes can happen in a safe thread
                downloaded_images: list[tuple[str, bytes]] = []
                if image_urls and not dry_run and not skip_image_download:
                    try:
                        sess = requests.Session()
                        req_headers = {
                            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
                            "Accept": "image/avif,image/webp,image/*,*/*;q=0.8",
                            "Referer": url,
                        }
                        if cookie_string:
                            req_headers["Cookie"] = cookie_string
                        for j, img_url in enumerate(image_urls, start=1):
                            try:
                                r = sess.get(img_url, headers=req_headers, timeout=20)
                                if r.status_code == 200 and r.content:
                                    fname = f"listing_{external_id or 'noid'}_{j}.jpg"
                                    downloaded_images.append((fname, r.content))
                                    if debug:
                                        self.stdout.write(f"Downloaded image {j}/{len(image_urls)} ({len(r.content)} bytes)")
                                else:
                                    if debug:
                                        self.stdout.write(f"Skipped image {j}: status={r.status_code}")
                            except Exception as e:
                                if debug:
                                    self.stdout.write(f"Download failed for {img_url}: {e}")
                    except Exception as e:
                        dbg(f"Image download session failed: {e}")

                if dry_run:
                    self.stdout.write(
                        f"[{idx}] DRY: title='{listing.title}' price={listing.price} city={listing.city} state={listing.state} address={listing.address}"
                    )
                    if connection.in_atomic_block:
                        transaction.set_rollback(True)
                else:
                    dbg("Saving to DB and ensuring images" if existing_listing else "Saving new listing to DB")
                    exc_holder = {}

                    def _thread_target():
                        try:
                            close_old_connections()
                            listing.save(skip_geocode=skip_geocode)
                            # If existing, verify images; if missing or broken, (re)attach
                            def images_need_fix(l):
                                try:
                                    imgs = list(l.images.all())
                                    if not imgs:
                                        return True
                                    for im in imgs:
                                        f = getattr(im, 'image', None)
                                        name = getattr(f, 'name', None) if f else None
                                        if not f or not name:
                                            return True
                                        try:
                                            if not f.storage.exists(name):
                                                return True
                                        except Exception:
                                            return True
                                    return False
                                except Exception:
                                    return True

                            if not no_images:
                                if existing_listing:
                                    if images_need_fix(listing) and downloaded_images:
                                        # Remove broken images only (or all if none valid)
                                        for im in list(listing.images.all()):
                                            try:
                                                f = getattr(im, 'image', None)
                                                name = getattr(f, 'name', None) if f else None
                                                missing = (not f or not name)
                                                try:
                                                    if not missing:
                                                        missing = not f.storage.exists(name)
                                                except Exception:
                                                    missing = True
                                                if missing:
                                                    im.delete()
                                            except Exception:
                                                pass
                                        # If still no images, attach downloads
                                        if listing.images.count() == 0:
                                            for i_img, (fname, data) in enumerate(downloaded_images):
                                                try:
                                                    img = ListingImage(listing=listing, order=i_img, is_primary=(i_img == 0))
                                                    img.image.save(fname, ContentFile(data), save=True)
                                                except Exception:
                                                    pass
                                else:
                                    if downloaded_images:
                                        for i_img, (fname, data) in enumerate(downloaded_images):
                                            try:
                                                img = ListingImage(listing=listing, order=i_img, is_primary=(i_img == 0))
                                                img.image.save(fname, ContentFile(data), save=True)
                                            except Exception:
                                                pass
                        except BaseException as e:
                            exc_holder["exc"] = e
                        finally:
                            close_old_connections()

                    t = threading.Thread(target=_thread_target, name="listing-save-thread", daemon=True)
                    t.start()
                    t.join()
                    if "exc" in exc_holder:
                        raise exc_holder["exc"]
                    if existing_listing:
                        updated += 1
                        self.stdout.write(self.style.SUCCESS(f"[{idx}] Updated listing id={listing.id} ({lookup_source}) images verified"))
                    else:
                        created += 1
                        self.stdout.write(self.style.SUCCESS(f"[{idx}] Created listing id={listing.id} title='{listing.title}'"))

                # Close page and delay between requests with tick logs in debug mode
                try:
                    page.close()
                except Exception:
                    pass
                if delay > 0:
                    if debug and delay >= 1.0:
                        secs = int(delay)
                        frac = delay - secs
                        self.stdout.write(f"Sleeping {delay:.1f}s...")
                        for i in range(secs):
                            time.sleep(1)
                            dbg(f"sleep tick {i+1}/{secs}")
                        if frac > 0:
                            time.sleep(frac)
                    else:
                        time.sleep(delay)

            context.close()
            browser.close()

        self.stdout.write(self.style.SUCCESS(f"Done. Created={created}, Updated={updated}, Skipped={skipped}, Total={len(urls)}"))
