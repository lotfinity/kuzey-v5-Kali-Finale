# Changelog

All notable changes to this project will be documented here.

This changelog was introduced on 2026-07-08 after part of the project history
already existed. Older entries are reconstructed from git commit messages,
existing documentation, and visible repository state, so some details may be
incomplete.

## [Unreleased]

### Added

- Added a dedicated listing investment portfolio page for listing 105 /
  Sahibinden 1314528782.
- Added portfolio routes under the localized listing URLs.
- Added a Leaflet portfolio map with the subject listing, TUYAP, and nearby
  Airbnb comparison listings.
- Added Swiper cards carousel support for nearby Airbnb comparison listings.
- Added richer Airbnb comparison rows/cards with thumbnail image, distance,
  title, property/spec line, guest capacity, trust signals, host review count,
  years hosting, availability badges, 30-day total, nightly equivalent, and
  Airbnb links.
- Added fresh Airbnb comparison/detail data for Gokevler and Esenyurt pricing
  analysis, including host and availability fields where the API provided them.
- Added TUYAP fair-calendar demand context and strategic-location notes to the
  portfolio view.
- Added rentability calculations based on the restored 30-day gross Airbnb comp
  model.
- Added reusable portfolio analysis service for dynamic single-listing portfolio
  pages.
- Added `build_listing_portfolios` management command to inspect a listing or
  rank the best portfolio-ready rentable flats on demand.

### Changed

- Expanded portfolio Airbnb comparison logic to use host metrics, guest capacity,
  images, rating/review signals, availability, and listing badges.
- Restored the prior portfolio rentability assumptions after availability-based
  calendar logic proved too restrictive for the current analysis.
- Refactored the one-off listing 105 portfolio into one reusable view, one
  reusable template, and shared portfolio logic for any listing with coordinates.
- Restarted the public Django runserver on port 9009 after adding the portfolio
  URL patterns.

### Verified

- `python manage.py check` passes.
- The public portfolio URL returns HTTP 200.
- Mobile Playwright verification loaded the portfolio and confirmed the Swiper
  cards interaction works.

### Known Issues

- Existing base-template browser console errors still reference missing
  `countUp.umd.js` and favicon assets.
- Airbnb availability details are available for the requested stay window, but
  the current API data is not a full forward-looking booking calendar.

## [2026-06-17]

### Changed

- Show unclustered MapLibre price markers.

## [2026-06-16]

### Added

- Added OpenClaw project metadata and agent guidance under `.openclaw/`.
- Added detailed WhatsApp widget changelog documentation.
- Added Airbnb API sample payloads for Istanbul, Esenyurt, Kyrenia, and listing
  detail requests.
- Added MapLibre frontend assets for the new map experience.
- Added WhatsApp widget frontend assets.
- Added rentability group SVG assets.
- Added Baton locale/static assets.

### Changed

- Updated ASGI, settings, distill, and URL wiring for the expanded frontend and
  static build surface.
- Updated MapLibre, WhatsApp, and new frontend static files.
- Removed generated `distill_output` artifacts from the repository.

## [2025-12-02]

### Added

- Added OpenAPI 3.1 spec endpoint for the chatbot API at
  `/api/bot/openapi.json`.
- Added AI chatbot API endpoints for customer-service bot integrations.
- Added project showcase pages with stats, tutorial carousel, nearby locations,
  and admin widget support.
- Added Baton admin distribution/static files.
- Added Turkish and French translation assets and compiled message files.
- Added Docker/static deployment support.

### Fixed

- Fixed Baton `baton.min.js` 404s by adding the required distribution files.
- Fixed collectstatic failures by adding missing static files and correcting font
  references.
- Removed missing sourcemap references from static assets, including
  `leaflet.markercluster.js`.
- Adjusted the Dockerfile so static files are treated as pre-built local assets
  instead of running collectstatic during image build.

## [2025-12-01]

### Added

- Imported the v5.0 baseline of the Coralcity real-estate Django application,
  including listings, realtors, contacts/inquiries, search, admin, and static
  site build support.
