# Tools & Commands for Kuzey Emlak

## 1. Django Management Commands

All commands are run as: `venv/bin/python manage.py <command> [args]`

### Import Pipeline
| Command | Purpose | Key Flags |
|---------|---------|-----------|
| `import_listings` | CSV import | `--csv-file`, `--dry-run` |
| `import_listings_from_links` | Sahibinden URL import (requests) | URLs from stdin |
| `import_listings_with_playwright` | Full Playwright scraper | `--single-url`, `--csv-file`, `--headed`, `--delay` |
| `import_listing_from_html` | Single listing from local HTML | `<file.html>` |
| `import_hot_listings` | Hot deals JSON import | `--file` |
| `import_android_results` | Android automation JSON | `<file>` |

### Airbnb Pipeline
| Command | Purpose | Key Flags |
|---------|---------|-----------|
| `fetch_airbnb_listings` | Fetch single market from Omkar Cloud API | `--destination`, `--arrival-date`, `--page-number`, `--currency-code` |
| `fetch_airbnb_markets` | Batch fetch across medical-core districts | `--district`, `--pages`, `--call-budget` |
| `calibrate_listing_rents` | Estimate rents from nearby Airbnb comps | `--apply`, `--factor`, `--min-comps`, `--radii-km`, `--listing-id` |
| `score_investment_targets` | ROI scoring for sale listings | `--budget`, `--json`, `--limit` |

### Android Sync Pipeline
| Command | Purpose | Key Flags |
|---------|---------|-----------|
| `sync_android_missing_listings` | Find missing listings from Sahibinden index | `--max-pages`, `--batch-label` |
| `sync_android_listing_phones` | Extract phone numbers | `--details`, `--max-pages` |
| `sync_android_listing_images` | Capture listing images | `--max-pages` |
| `export_android_listing_targets` | Export missing external IDs as JSON | — |
| `export_android_phone_targets` | Export listings needing phone extraction | — |
| `export_android_image_targets` | Export listings without images | — |

### Geocoding & Maps
| Command | Purpose | Key Flags |
|---------|---------|-----------|
| `geocode_listings` | Geocode all listings | — |
| `geocode_missing_listings` | Geocode only listings without coords | — |
| `generate_listing_maps` | Pre-generate Leaflet map HTML per listing | — |

### Data Quality
| Command | Purpose |
|---------|---------|
| `resolve_listing_phone_entries` | Link PhoneEntry to Listing by external_id |
| `backfill_listing_phone_entries` | Create audit rows for existing phones |

### Translation
| Command | Purpose |
|---------|---------|
| `translate_titles_french` | Bulk title translation (Turkish→French) |
| `translate_titles_interactive` | Interactive manual title translation |

---

## 2. Django Shell / Shell Plus

```bash
# Activate venv first
source venv/bin/activate

# Standard Django shell
python manage.py shell

# Advanced shell_plus (auto-imports all models)
# Requires: pip install django-extensions
python manage.py shell_plus
python manage.py shell_plus --print-sql  # See SQL queries
```

### Shell One-Liners
```python
# Count all listings
Listing.objects.count()

# Count published listings
Listing.objects.filter(is_published=True).count()

# Find listings missing coordinates
Listing.objects.filter(is_published=True, latitude__isnull=True).count()

# Recent listings
Listing.objects.filter(is_published=True).order_by('-list_date')[:10]

# Airbnb comps count
AirbnbListing.objects.count()

# Check a listing's rent calibration
l = Listing.objects.get(id=1)
print(l.estimated_monthly_rent_try, l.airbnb_comp_count, l.airbnb_comp_median_try)

# Find top scored investment targets
from listings.investor import build_investor_summary
summary = build_investor_summary()
for i, item in enumerate(summary['ranked'][:5]):
    print(f"{i+1}. #{item['id']} {item['title'][:50]} | ROI {item['scenarios']['operator']['roi_percent']}%")

# Currency rates
cs = CurrencySettings.load()
print(f"USD/TRY: {cs.try_to_usd}, EUR/TRY: {cs.try_to_eur}")

# Get admin URL for a listing
from django.urls import reverse
print(reverse('admin:listings_listing_change', args=[1]))
```

---

## 3. WhatsApp Integration (atomic-waha-v3)

### REST API Endpoints (via Django)
| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/whatsapp/listing/<id>/send` | POST | Send a message about a listing |
| `/api/whatsapp/listing/<id>/conversation` | GET | Get conversation for listing |
| `/api/whatsapp/conversations` | GET | List all conversations |
| `/api/whatsapp/conversation/<id>/messages` | GET | Get messages in conversation |
| `/api/whatsapp/conversation/<id>/send` | POST | Send message in conversation |
| `/api/whatsapp/listing/<id>/suggest` | POST | Get AI-suggested reply |
| `/api/whatsapp/webhook` | POST | WAHA webhook receiver |

### Plugin Configuration
The atomic-waha-v3 plugin is already configured in `~/.openclaw/openclaw.json`:
- **Base URL**: `https://waha-gows.whatsynaptic.com`
- **Session**: `user-905014614767`
- **Webhook**: `https://gateway.whatsynaptic.com/webhooks/atomic-waha-v3`

### Typical Outreach Workflow
1. Find listings needing contact — listing has a phone but no WhatsApp conversation yet
2. Use `manage.py shell_plus` to query listings without conversations
3. Send initial message via API or atomic-waha-v3 plugin
4. Track replies via WebSocket/Webhook
5. Use AI suggest endpoint for reply drafting

---

## 4. Management Command Quick Reference

### Import Flow (Full Pipeline)
```bash
# Step 1: Sync missing listings from Sahibinden index
venv/bin/python manage.py sync_android_missing_listings --max-pages 5 --batch-label medical-core-small-units

# Step 2: Export targets and extract phones
venv/bin/python manage.py export_android_phone_targets
venv/bin/python manage.py sync_android_listing_phones --details --max-pages 5

# Step 3: Capture images
venv/bin/python manage.py export_android_image_targets
venv/bin/python manage.py sync_android_listing_images --max-pages 5

# Step 4: Geocode
venv/bin/python manage.py geocode_missing_listings

# Step 5: Fetch Airbnb comps
venv/bin/python manage.py fetch_airbnb_markets --pages 2 --call-budget 60

# Step 6: Calibrate rents
venv/bin/python manage.py calibrate_listing_rents --apply --radii-km 1.5,3,5

# Step 7: Score investments
venv/bin/python manage.py score_investment_targets --budget 3500000 --limit 20
```

### Investor Dashboard Scoring
```bash
# Default scoring (top 10)
venv/bin/python manage.py score_investment_targets

# Full JSON output
venv/bin/python manage.py score_investment_targets --json

# Custom budget and limit
venv/bin/python manage.py score_investment_targets --budget 5000000 --limit 30 --json

# With custom occupancy assumptions
venv/bin/python manage.py score_investment_targets --base-occupancy-percent 75 --operator-occupancy-uplift-percent 15
```
