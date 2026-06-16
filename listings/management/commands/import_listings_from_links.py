import csv
import re
import time
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import requests
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from listings.models import Listing
from realtors.models import Realtor


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


def parse_location_from_breadcrumb(soup):
    """Extract city, district, neighborhood from breadcrumb anchors.
    Returns (city, district, neighborhood) or (None, None, None).
    """
    anchors = soup.select('a[data-click-label^="Adres Breadcrumb"]')
    texts = [a.get_text(strip=True) for a in anchors if a]
    texts = [t for t in texts if t]
    if len(texts) >= 3:
        return texts[0], texts[1], texts[-1]
    meta = soup.find('meta', attrs={'name': 'description'})
    if meta and meta.get('content'):
        m = re.search(r"([\wÇĞİÖŞÜçğıöşü\s\.-]+?)\s+Mh\.?\s+([\wÇĞİÖŞÜçğıöşü\s\.-]+?)\s+([\wÇĞİÖŞÜçğıöşü\s\.-]+)", meta['content'])
        if m:
            neighborhood = (m.group(1) + ' Mh.').strip()
            district = m.group(2).strip()
            city = m.group(3).strip()
            return city, district, neighborhood
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
    help = "Import listings from a CSV file of Sahibinden URLs. One URL per line, or a CSV with a 'url' column."

    def add_arguments(self, parser):
        parser.add_argument(
            "csv_path",
            nargs="?",
            default="listings/links.csv",
            help="Path to CSV file containing URLs",
        )
        parser.add_argument("--realtor-id", type=int, required=True, help="Realtor ID to assign to listings")
        parser.add_argument("--default-city", type=str, default="", help="Default city if not found")
        parser.add_argument("--default-state", type=str, default="", help="Default state/district if not found")
        parser.add_argument("--default-zipcode", type=str, default="", help="Default zipcode if not found")
        parser.add_argument("--default-address", type=str, default="", help="Default address if not found")
        parser.add_argument("--delay", type=float, default=1.5, help="Seconds to wait between requests")
        parser.add_argument("--dry-run", action="store_true", help="Parse and show without saving to DB")
        parser.add_argument("--debug", action="store_true", help="Verbose debug logs of every step")
        parser.add_argument(
            "--save-html-dir",
            type=str,
            default="",
            help="If set, save fetched HTML files into this directory for inspection",
        )
        parser.add_argument(
            "--cookie",
            type=str,
            default="",
            help="Optional Cookie header value to pass (copy from a logged-in browser)",
        )

    def read_urls(self, path: Path) -> list[str]:
        text = path.read_text(encoding="utf-8", errors="ignore")
        # Try CSV with header first
        try:
            rows = list(csv.DictReader(text.splitlines()))
            if rows and "url" in rows[0]:
                urls = [r.get("url", "").strip() for r in rows]
                return [u for u in urls if u and not u.startswith("#")]
        except Exception:
            pass
        # Fallback: one URL per line (comma-separated tolerated -> take first cell)
        urls: list[str] = []
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            first = line.split(",")[0].strip()
            if first:
                urls.append(first)
        return urls

    @transaction.atomic
    def handle(self, *args, **options):
        csv_path = Path(options["csv_path"])
        realtor_id = options["realtor_id"]
        default_city = options["default_city"]
        default_state = options["default_state"]
        default_zipcode = options["default_zipcode"]
        default_address = options["default_address"]
        delay = float(options["delay"]) or 0.0
        dry_run = options["dry_run"]
        debug = bool(options.get("debug"))
        save_dir = Path(options.get("save_html_dir") or "") if options.get("save_html_dir") else None
        cookie = options.get("cookie") or ""

        def dbg(msg: str):
            if debug:
                ts = datetime.now().strftime("%H:%M:%S")
                self.stdout.write(f"[{ts}] {msg}")

        if not csv_path.exists():
            raise CommandError(f"CSV not found: {csv_path}")

        realtor = Realtor.objects.filter(id=realtor_id).first()
        if not realtor:
            raise CommandError(f"Realtor not found with id={realtor_id}")

        try:
            from bs4 import BeautifulSoup
        except Exception as e:
            raise CommandError(
                "beautifulsoup4 is required for this command. Please add it to requirements and install."
            ) from e

        urls = self.read_urls(csv_path)
        if not urls:
            self.stdout.write(self.style.WARNING("No URLs found in CSV"))
            return

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Referer": "https://www.sahibinden.com/",
            "Connection": "keep-alive",
        }
        if cookie:
            headers["Cookie"] = cookie
            dbg("Custom Cookie header provided for requests")

        created = 0
        skipped = 0

        for idx, url in enumerate(urls, start=1):
            dbg(f"[{idx}/{len(urls)}] Fetching URL: {url}")
            try:
                resp = requests.get(url, headers=headers, timeout=20)
                dbg(f"HTTP status: {resp.status_code}; content length: {len(resp.text)}")
                if resp.status_code != 200:
                    self.stdout.write(self.style.WARNING(f"[{idx}] HTTP {resp.status_code} -> skip: {url}"))
                    skipped += 1
                    continue
                html = resp.text
            except requests.RequestException as e:
                self.stdout.write(self.style.WARNING(f"[{idx}] Request failed: {e} -> {url}"))
                skipped += 1
                continue

            if save_dir:
                try:
                    save_dir.mkdir(parents=True, exist_ok=True)
                    safe_name = re.sub(r"[^a-zA-Z0-9_-]", "_", url)[:180] + ".html"
                    (save_dir / safe_name).write_text(html, encoding="utf-8")
                    dbg(f"Saved HTML to: {(save_dir / safe_name)}")
                except Exception as e:
                    dbg(f"Failed to save HTML: {e}")

            dbg("Parsing HTML with BeautifulSoup")
            soup = BeautifulSoup(html, "html.parser")

            # Title
            title = ""
            dbg("Selecting title with CSS 'div.classifiedDetailTitle > h1'")
            node = soup.select_one("div.classifiedDetailTitle > h1")
            if node:
                title = node.get_text(strip=True)
            dbg(f"Title: {title!r}")
            if not title:
                dbg("Title not found via CSS; falling back to first <h1>")
                h1 = soup.find("h1")
                title = h1.get_text(strip=True) if h1 else ""
                dbg(f"Fallback title: {title!r}")

            # Price
            price_text = ""
            dbg("Selecting price with CSS 'div.classifiedInfo .classified-price-wrapper'")
            node = soup.select_one("div.classifiedInfo .classified-price-wrapper")
            if node:
                price_text = node.get_text(strip=True)
            dbg(f"Raw price text: {price_text!r}")
            price = clean_int_from_text(price_text)
            dbg(f"Parsed price (int): {price}")

            # Details list
            details: dict[str, str] = {}
            dbg("Collecting detail items from 'ul.classifiedInfoList > li'")
            for li in soup.select("ul.classifiedInfoList > li"):
                key_el = li.find("strong")
                val_el = li.find("span")
                if not key_el or not val_el:
                    continue
                key = key_el.get_text(strip=True)
                val = val_el.get_text(strip=True)
                if key:
                    details[key] = val
                    dbg(f"Detail: {key!r} -> {val!r}")

            property_type_raw = details.get("Emlak Tipi", "")
            deal_type, property_type = parse_deal_and_type(property_type_raw)
            dbg(f"Property type raw: {property_type_raw!r} -> mapped: {property_type!r}")
            bedrooms = (details.get("Oda Sayısı", "") or details.get("Oda Sayisi", "")).strip()
            dbg(f"Bedrooms parsed: {bedrooms!r}")
            bathrooms = clean_int_from_text(details.get("Banyo Sayısı", "") or details.get("Banyo Sayisi", ""))
            dbg(f"Bathrooms parsed: {bathrooms}")
            m2_brut_text = details.get("m² (Brüt)", "") or details.get("m2 (Brut)", "")
            try:
                m2_brut = int(re.sub(r"\D", "", m2_brut_text)) if m2_brut_text else 0
            except ValueError:
                m2_brut = 0
            sqft = int(round(m2_brut * 10.7639)) if m2_brut else 0
            dbg(f"m² (Brüt): {m2_brut_text!r} -> m2={m2_brut} -> sqft={sqft}")
            list_date = parse_tr_date(details.get("İlan Tarihi", "") or details.get("Ilan Tarihi", ""))
            ad_date = list_date
            external_id = (details.get("İlan No") or details.get("Ilan No") or "").strip()
            dbg(f"List date parsed: {list_date}")

            # Map link and coordinates
            lat = lon = None
            dbg("Looking for map link 'div.getDirectionsButton > a'")
            a = soup.select_one("div.getDirectionsButton > a")
            if a and a.has_attr("href"):
                dbg(f"Found map href: {a['href']}")
                lat, lon = extract_lat_lon_from_url(a["href"])
                dbg(f"Parsed coordinates: lat={lat}, lon={lon}")

            # Address/location: try breadcrumbs first
            dbg("Parsing breadcrumbs for location")
            city_b, district_b, neighborhood_b = parse_location_from_breadcrumb(soup)
            dbg(f"Breadcrumbs -> city={city_b!r}, district={district_b!r}, neighborhood={neighborhood_b!r}")
            address = neighborhood_b or default_address
            city = city_b or default_city
            state = district_b or default_state
            zipcode = default_zipcode

            # Additional attributes
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

            # Extra details in description
            summary_items = [
                ("Bina Yaşı", building_age),
                ("Bulunduğu Kat", floor_number),
                ("Kat Sayısı", floors_total),
                ("Isıtma", heating),
                ("Balkon", balcony),
                ("Eşyalı", "Evet" if furnished else ("Hayır" if furnished is False else "")),
                ("Aidat", maintenance_fee),
            ]
            description_parts = [f"{k}: {v}" for k, v in summary_items if v not in (None, "")]
            description = " | ".join(description_parts)

            dbg("Constructing Listing instance with parsed fields")
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
            )

            if lat is not None and lon is not None:
                listing.latitude = lat
                listing.longitude = lon
            if list_date:
                listing.list_date = list_date

            if dry_run:
                self.stdout.write(f"[{idx}] DRY: title='{listing.title}' price={listing.price} url={url}")
                dbg(f"Final fields -> city={listing.city}, state={listing.state}, address={listing.address}, lat={listing.latitude}, lon={listing.longitude}")
                transaction.set_rollback(True)
            else:
                dbg("Saving listing to database")
                listing.save()
                created += 1
                self.stdout.write(self.style.SUCCESS(f"[{idx}] Created listing id={listing.id} title='{listing.title}'"))

            if delay > 0:
                if debug and delay >= 1.0:
                    secs = int(delay)
                    frac = delay - secs
                    self.stdout.write(f"Sleeping {delay:.1f}s between requests...")
                    for i in range(secs):
                        time.sleep(1)
                        dbg(f"sleep tick {i+1}/{secs}")
                    if frac > 0:
                        time.sleep(frac)
                else:
                    time.sleep(delay)

        self.stdout.write(self.style.SUCCESS(f"Done. Created={created}, skipped={skipped}, total={len(urls)}"))
