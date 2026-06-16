(function () {
  var root = document.getElementById('maplibre-app');
  if (!root || !window.maplibregl) return;

  var shell = document.getElementById('ml-shell');
  var mapEl = document.getElementById('ml-map');
  var listEl = document.getElementById('ml-list');
  var selectedEl = document.getElementById('ml-selected');
  var sheet = document.getElementById('ml-mobile-sheet');
  var sheetHandle = document.getElementById('ml-sheet-handle');
  var sheetSelectedEl = document.getElementById('ml-sheet-selected');
  var sheetListEl = document.getElementById('ml-sheet-list');
  var statusEl = document.getElementById('ml-status');
  var airbnbBtn = document.getElementById('ml-airbnb');
  var fitBtn = document.getElementById('ml-fit');
  var fullscreenBtn = document.getElementById('ml-fullscreen');
  var langPrefix = root.dataset.langPrefix || '/en/';

  var state = {
    activeDataset: 'listings',
    activeFilter: 'all',
    activeStyle: 'dark',
    selectedId: null,
    listings: [],
    airbnb: [],
    current: []
  };

  var layerIds = {
    clusters: 'kuzey-clusters',
    clusterCount: 'kuzey-cluster-count',
    points: 'kuzey-points',
    labels: 'kuzey-point-labels',
    selected: 'kuzey-selected-point'
  };

  var mapStyles = {
    light: rasterStyle('light', cartoTiles('light_all')),
    dark: rasterStyle('dark', cartoTiles('dark_all'))
  };

  var map = new maplibregl.Map({
    container: mapEl,
    style: mapStyles.dark,
    center: [28.67, 41.02],
    zoom: 11,
    attributionControl: false
  });
  map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'bottom-right');

  function cartoTiles(styleName) {
    return ['a', 'b', 'c', 'd'].map(function (subdomain) {
      return 'https://' + subdomain + '.basemaps.cartocdn.com/' + styleName + '/{z}/{x}/{y}.png';
    });
  }

  function rasterStyle(id, tiles) {
    return {
      version: 8,
      glyphs: 'https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf',
      sources: {
        carto: {
          type: 'raster',
          tiles: tiles,
          tileSize: 256,
          attribution: '&copy; OpenStreetMap &copy; CARTO'
        }
      },
      layers: [
        {
          id: id + '-raster',
          type: 'raster',
          source: 'carto'
        }
      ]
    };
  }

  function setStatus(text) {
    if (statusEl) statusEl.querySelector('strong').textContent = text;
  }

  function escapeHtml(value) {
    return String(value == null ? '' : value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  function fmtCurrency(value, currency) {
    if (value == null || value === '') return '';
    var code = currency || 'TRY';
    if (code === 'TRY' && window.KuzeyCurrency) return window.KuzeyCurrency.format(value);
    try {
      return new Intl.NumberFormat(code === 'TRY' ? 'tr-TR' : 'en-US', {
        style: 'currency',
        currency: code,
        maximumFractionDigits: code === 'TRY' ? 0 : 0
      }).format(value);
    } catch (err) {
      return String(value);
    }
  }

  function priceText(p) {
    var label = fmtCurrency(p.price, p.currency || 'TRY');
    if (!label) return '';
    return p.source === 'airbnb' ? label + ' / July stay' : label;
  }

  function roomSizeOf(p) {
    if (p.source === 'airbnb') {
      var bedrooms = parseInt(p.bedrooms || 0, 10);
      return bedrooms ? bedrooms + '+1' : '1+0';
    }
    var raw = String(p.rooms_text || '').toLowerCase().replace(/\s+/g, '');
    var match = raw.match(/\d+\+\d+/);
    return match ? match[0] : '';
  }

  function detailUrl(p) {
    if (p.source === 'airbnb') return p.booking_url || p.listing_url || p.url || '#';
    return langPrefix + 'new/listing/' + (p.id || '') + '/';
  }

  function directionsUrl(p) {
    return 'https://www.google.com/maps/dir/?api=1&destination=' + encodeURIComponent(p.lat + ',' + p.lng);
  }

  function normalizeFeature(feature) {
    var coords = feature && feature.geometry ? feature.geometry.coordinates : null;
    var p = Object.assign({}, feature.properties || {});
    if (!coords || coords.length < 2) return null;
    p.lng = Number(coords[0]);
    p.lat = Number(coords[1]);
    if (!Number.isFinite(p.lng) || !Number.isFinite(p.lat)) return null;
    p.id = String(p.id);
    p.roomSize = roomSizeOf(p);
    p.priceLabel = priceText(p);
    p.image = Array.isArray(p.photos) && p.photos.length ? p.photos[0] : (p.photo_url || '');
    p.detailUrl = detailUrl(p);
    p.directionsUrl = directionsUrl(p);
    return {
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [p.lng, p.lat] },
      properties: p
    };
  }

  function featureCollection(features) {
    return { type: 'FeatureCollection', features: features || [] };
  }

  function filteredFeatures() {
    var base = state.activeDataset === 'airbnb' ? state.airbnb : state.listings;
    return base.filter(function (feature) {
      return state.activeFilter === 'all' || feature.properties.roomSize === state.activeFilter;
    });
  }

  function selectedFeatureCollection() {
    var found = state.current.find(function (feature) {
      return String(feature.properties.id) === String(state.selectedId);
    });
    return featureCollection(found ? [found] : []);
  }

  function sourceData() {
    return featureCollection(state.current);
  }

  function addMapLayers() {
    if (!map.getSource('items')) {
      map.addSource('items', {
        type: 'geojson',
        data: sourceData(),
        cluster: true,
        clusterRadius: 54,
        clusterMaxZoom: 15
      });
    }

    if (!map.getSource('selected-item')) {
      map.addSource('selected-item', {
        type: 'geojson',
        data: selectedFeatureCollection()
      });
    }

    if (!map.getLayer(layerIds.clusters)) {
      map.addLayer({
        id: layerIds.clusters,
        type: 'circle',
        source: 'items',
        filter: ['has', 'point_count'],
        paint: {
          'circle-color': state.activeDataset === 'airbnb' ? '#ff385c' : '#a38344',
          'circle-radius': ['step', ['get', 'point_count'], 23, 12, 29, 32, 35],
          'circle-stroke-width': 3,
          'circle-stroke-color': '#ffffff',
          'circle-opacity': .96
        }
      });
    }

    if (!map.getLayer(layerIds.clusterCount)) {
      map.addLayer({
        id: layerIds.clusterCount,
        type: 'symbol',
        source: 'items',
        filter: ['has', 'point_count'],
        layout: {
          'text-field': ['get', 'point_count_abbreviated'],
          'text-size': 14,
          'text-font': ['Noto Sans Regular']
        },
        paint: {
          'text-color': '#ffffff'
        }
      });
    }

    if (!map.getLayer(layerIds.points)) {
      map.addLayer({
        id: layerIds.points,
        type: 'circle',
        source: 'items',
        filter: ['!', ['has', 'point_count']],
        paint: {
          'circle-color': [
            'case',
            ['==', ['get', 'source'], 'airbnb'],
            '#ff385c',
            '#191715'
          ],
          'circle-radius': [
            'interpolate',
            ['linear'],
            ['zoom'],
            9, 7,
            13, 10,
            16, 14
          ],
          'circle-stroke-width': 3,
          'circle-stroke-color': '#ffffff',
          'circle-opacity': .96
        }
      });
    }

    if (!map.getLayer(layerIds.labels)) {
      map.addLayer({
        id: layerIds.labels,
        type: 'symbol',
        source: 'items',
        filter: ['!', ['has', 'point_count']],
        minzoom: 13,
        layout: {
          'text-field': ['coalesce', ['get', 'priceLabel'], ''],
          'text-font': ['Noto Sans Regular'],
          'text-size': 11,
          'text-offset': [0, 1.65],
          'text-anchor': 'top',
          'text-allow-overlap': false
        },
        paint: {
          'text-color': '#171513',
          'text-halo-color': '#ffffff',
          'text-halo-width': 1.5
        }
      });
    }

    if (!map.getLayer(layerIds.selected)) {
      map.addLayer({
        id: layerIds.selected,
        type: 'circle',
        source: 'selected-item',
        paint: {
          'circle-color': 'rgba(255,255,255,0)',
          'circle-radius': 18,
          'circle-stroke-width': 4,
          'circle-stroke-color': state.activeDataset === 'airbnb' ? '#ff385c' : '#a38344'
        }
      });
    }
  }

  function updateMapPaint() {
    if (!map.getLayer(layerIds.clusters)) return;
    map.setPaintProperty(layerIds.clusters, 'circle-color', state.activeDataset === 'airbnb' ? '#ff385c' : '#a38344');
    map.setPaintProperty(layerIds.selected, 'circle-stroke-color', state.activeDataset === 'airbnb' ? '#ff385c' : '#a38344');
  }

  function setSourceData() {
    state.current = filteredFeatures();
    if (map.getSource('items')) map.getSource('items').setData(sourceData());
    if (map.getSource('selected-item')) map.getSource('selected-item').setData(selectedFeatureCollection());
    updateMapPaint();
    renderLists();
    setStatus(state.current.length + (state.activeDataset === 'airbnb' ? ' Airbnb rentals visible' : ' listings visible'));
  }

  function fitToData(options) {
    var features = state.current;
    if (!features.length) {
      map.easeTo({ center: [28.67, 41.02], zoom: 11 });
      return;
    }
    var bounds = new maplibregl.LngLatBounds();
    features.forEach(function (feature) {
      bounds.extend(feature.geometry.coordinates);
    });
    map.fitBounds(bounds, Object.assign({
      padding: window.innerWidth < 992
        ? { top: 150, right: 40, bottom: 220, left: 40 }
        : { top: 110, right: 70, bottom: 70, left: 70 },
      duration: 700,
      maxZoom: 15
    }, options || {}));
  }

  function cardHTML(p) {
    var isAirbnb = p.source === 'airbnb';
    return '' +
      (p.image ? '<img class="ml-card-img" src="' + escapeHtml(p.image) + '" alt="">' : '<div class="ml-card-img"></div>') +
      '<div>' +
        (isAirbnb ? '<div class="ml-brand"><i class="fa fa-bed"></i>Airbnb</div>' : '') +
        '<h2 class="ml-card-title">' + escapeHtml(p.title || 'Listing') + '</h2>' +
        (p.priceLabel ? '<div class="ml-card-price">' + escapeHtml(p.priceLabel) + '</div>' : '') +
        '<div class="ml-card-meta">' +
          '<span><i class="fa fa-location-dot"></i>' + escapeHtml(p.city || p.state || 'Esenyurt') + '</span>' +
          (p.rooms_text || p.bedrooms ? '<span><i class="fa fa-door-open"></i>' + escapeHtml(p.rooms_text || p.bedrooms) + '</span>' : '') +
          (p.m2_net ? '<span><i class="fa fa-ruler-combined"></i>' + escapeHtml(p.m2_net) + ' m2</span>' : '') +
          (isAirbnb && p.overall_rating ? '<span><i class="fa fa-star"></i>' + escapeHtml(p.overall_rating) + '</span>' : '') +
        '</div>' +
      '</div>';
  }

  function previewHTML(p) {
    if (!p) {
      return '<div class="ml-preview"><div class="ml-preview-img"></div><div><h2 class="ml-preview-title">Select a marker</h2><div class="ml-preview-meta">Tap a point on the map or choose a listing.</div></div></div>';
    }
    var isAirbnb = p.source === 'airbnb';
    var target = isAirbnb ? ' target="_blank" rel="noopener noreferrer"' : '';
    return '' +
      '<div class="ml-preview' + (isAirbnb ? ' is-airbnb' : '') + '">' +
        (p.image ? '<img class="ml-preview-img" src="' + escapeHtml(p.image) + '" alt="">' : '<div class="ml-preview-img"></div>') +
        '<div>' +
          (isAirbnb ? '<div class="ml-brand"><i class="fa fa-bed"></i>Airbnb</div>' : '') +
          '<h2 class="ml-preview-title">' + escapeHtml(p.title || 'Listing') + '</h2>' +
          (p.priceLabel ? '<div class="ml-preview-price">' + escapeHtml(p.priceLabel) + '</div>' : '') +
          '<div class="ml-preview-meta">' +
            '<span><i class="fa fa-location-dot"></i>' + escapeHtml(p.city || p.state || 'Esenyurt') + '</span>' +
            (p.rooms_text || p.bedrooms ? '<span><i class="fa fa-door-open"></i>' + escapeHtml(p.rooms_text || p.bedrooms) + '</span>' : '') +
            (p.bathrooms ? '<span><i class="fa fa-bath"></i>' + escapeHtml(p.bathrooms) + '</span>' : '') +
            (isAirbnb && p.review_count ? '<span><i class="fa fa-star"></i>' + escapeHtml(p.overall_rating || '') + ' · ' + escapeHtml(p.review_count) + '</span>' : '') +
          '</div>' +
          '<div class="ml-preview-actions">' +
            '<a class="ml-action" href="' + escapeHtml(p.detailUrl) + '"' + target + '><i class="fa fa-arrow-up-right-from-square"></i>' + (isAirbnb ? 'Airbnb' : 'Open') + '</a>' +
            '<a class="ml-action secondary" href="' + escapeHtml(p.directionsUrl) + '" target="_blank" rel="noopener noreferrer"><i class="fa fa-route"></i>Directions</a>' +
          '</div>' +
        '</div>' +
      '</div>';
  }

  function renderLists() {
    var selected = selectedFeature();
    selectedEl.innerHTML = previewHTML(selected ? selected.properties : null);
    sheetSelectedEl.innerHTML = previewHTML(selected ? selected.properties : null);

    listEl.innerHTML = '';
    sheetListEl.innerHTML = '';
    state.current.forEach(function (feature) {
      var p = feature.properties;
      var card = document.createElement('button');
      card.type = 'button';
      card.className = 'ml-card' + (p.source === 'airbnb' ? ' is-airbnb' : '') + (String(p.id) === String(state.selectedId) ? ' is-selected' : '');
      card.dataset.id = p.id;
      card.innerHTML = cardHTML(p);
      card.addEventListener('click', function () { selectFeatureById(p.id, true); });
      listEl.appendChild(card);

      var mobileCard = card.cloneNode(true);
      mobileCard.addEventListener('click', function () { selectFeatureById(p.id, true); openSheet(true); });
      sheetListEl.appendChild(mobileCard);
    });
  }

  function selectedFeature() {
    return state.current.find(function (feature) {
      return String(feature.properties.id) === String(state.selectedId);
    });
  }

  function selectFeatureById(id, fly) {
    state.selectedId = String(id);
    var feature = selectedFeature();
    if (!feature) return;
    if (map.getSource('selected-item')) {
      map.getSource('selected-item').setData(selectedFeatureCollection());
    }
    renderLists();
    if (fly) {
      map.easeTo({
        center: feature.geometry.coordinates,
        zoom: Math.max(map.getZoom(), 14),
        duration: 650,
        padding: window.innerWidth < 992 ? { bottom: 190 } : { left: 260 }
      });
    }
    openSheet(true);
  }

  function openSheet(open) {
    if (!sheet) return;
    sheet.classList.toggle('is-open', !!open);
  }

  function setDataset(dataset) {
    state.activeDataset = dataset === 'airbnb' ? 'airbnb' : 'listings';
    state.selectedId = null;
    shell.classList.toggle('is-airbnb', state.activeDataset === 'airbnb');
    airbnbBtn.setAttribute('aria-pressed', state.activeDataset === 'airbnb' ? 'true' : 'false');
    airbnbBtn.innerHTML = state.activeDataset === 'airbnb' ? '<i class="fa fa-map-location-dot"></i>' : '<i class="fa fa-bed"></i>';
    state.activeFilter = 'all';
    document.querySelectorAll('.ml-chip').forEach(function (btn) {
      btn.classList.toggle('is-active', btn.dataset.filter === 'all');
    });
    setSourceData();
    fitToData();
  }

  function setFilter(filter) {
    state.activeFilter = filter || 'all';
    state.selectedId = null;
    document.querySelectorAll('.ml-chip').forEach(function (btn) {
      btn.classList.toggle('is-active', btn.dataset.filter === state.activeFilter);
    });
    setSourceData();
    fitToData();
  }

  function setMapStyle(styleName) {
    state.activeStyle = styleName === 'light' ? 'light' : 'dark';
    document.querySelectorAll('.ml-style-btn').forEach(function (btn) {
      btn.classList.toggle('is-active', btn.dataset.style === state.activeStyle);
    });
    map.setStyle(mapStyles[state.activeStyle]);
  }

  function fetchGeoJson(url) {
    return fetch(url).then(function (response) {
      if (!response.ok) throw new Error('Failed to load ' + url);
      return response.json();
    });
  }

  function loadData() {
    setStatus('Loading listings');
    return Promise.all([
      fetchGeoJson(root.dataset.listingsUrl),
      fetchGeoJson(root.dataset.airbnbUrl)
    ]).then(function (responses) {
      state.listings = (responses[0].features || []).map(normalizeFeature).filter(Boolean);
      state.airbnb = (responses[1].features || []).map(normalizeFeature).filter(Boolean);
      state.current = filteredFeatures();
      setSourceData();
      fitToData({ duration: 0 });
    }).catch(function (err) {
      console.warn(err);
      setStatus('Map data unavailable');
    });
  }

  map.on('load', function () {
    addMapLayers();
    loadData();
  });

  map.on('styledata', function () {
    if (!map.isStyleLoaded()) return;
    addMapLayers();
    setSourceData();
  });

  map.on('click', layerIds.clusters, function (event) {
    var features = map.queryRenderedFeatures(event.point, { layers: [layerIds.clusters] });
    var cluster = features[0];
    if (!cluster) return;
    map.getSource('items').getClusterExpansionZoom(cluster.properties.cluster_id, function (err, zoom) {
      if (err) return;
      map.easeTo({ center: cluster.geometry.coordinates, zoom: zoom, duration: 550 });
    });
  });

  map.on('click', layerIds.points, function (event) {
    var feature = event.features && event.features[0];
    if (!feature) return;
    selectFeatureById(feature.properties.id, true);
  });

  [layerIds.clusters, layerIds.points].forEach(function (layerId) {
    map.on('mouseenter', layerId, function () { map.getCanvas().style.cursor = 'pointer'; });
    map.on('mouseleave', layerId, function () { map.getCanvas().style.cursor = ''; });
  });

  document.querySelectorAll('.ml-chip').forEach(function (btn) {
    btn.addEventListener('click', function () { setFilter(btn.dataset.filter || 'all'); });
  });

  document.querySelectorAll('.ml-style-btn').forEach(function (btn) {
    btn.addEventListener('click', function () { setMapStyle(btn.dataset.style); });
  });

  airbnbBtn.addEventListener('click', function () {
    setDataset(state.activeDataset === 'airbnb' ? 'listings' : 'airbnb');
  });

  fitBtn.addEventListener('click', function () { fitToData(); });

  fullscreenBtn.addEventListener('click', function () {
    if (!document.fullscreenElement && shell.requestFullscreen) {
      shell.requestFullscreen();
    } else if (document.exitFullscreen) {
      document.exitFullscreen();
    }
  });

  document.addEventListener('fullscreenchange', function () {
    var active = document.fullscreenElement === shell;
    fullscreenBtn.setAttribute('aria-pressed', active ? 'true' : 'false');
    fullscreenBtn.innerHTML = active ? '<i class="fa fa-compress"></i>' : '<i class="fa fa-expand"></i>';
    setTimeout(function () { map.resize(); fitToData({ duration: 0 }); }, 180);
  });

  if (sheetHandle) {
    sheetHandle.addEventListener('click', function () {
      openSheet(!sheet.classList.contains('is-open'));
    });

    var startY = 0;
    sheetHandle.addEventListener('touchstart', function (event) {
      startY = event.touches && event.touches[0] ? event.touches[0].clientY : 0;
    }, { passive: true });
    sheetHandle.addEventListener('touchend', function (event) {
      var endY = event.changedTouches && event.changedTouches[0] ? event.changedTouches[0].clientY : startY;
      openSheet(endY < startY);
    }, { passive: true });
  }

  window.addEventListener('resize', function () {
    map.resize();
  });
})();
