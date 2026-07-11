"""btre URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/2.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.views.generic import TemplateView
from django.views.decorators.clickjacking import xframe_options_exempt
from listings import views as listing_views
# Make GraphQL optional to avoid import errors during static builds or incompatible versions
try:
    from graphene_django.views import GraphQLView  # type: ignore
    from blog.schema import schema  # noqa: F401
    _has_graphql = True
except Exception:
    _has_graphql = False
from pages import views as pages_views
from django.conf.urls.i18n import i18n_patterns
try:
    import baton  # noqa: F401
    _has_baton = True
except Exception:
    _has_baton = False


from django.conf.urls.static import static
from django.conf import settings

# Make Rosetta optional so URLs don't break if not installed
try:
    import rosetta  # noqa: F401
    _has_rosetta = True
except Exception:
    _has_rosetta = False

# Include django-distill URL patterns (static site generation)
from coralcity import distill_urls as distill

urlpatterns = [
    # Baton URLs (conditionally included)
    # If django-baton is installed, this exposes its assets and views
    # and styles the default Django admin.
    # The 'i18n/' path is where Django handles setting the language and should usually not be prefixed.
    path('i18n/', include('django.conf.urls.i18n')),
    # Public API (no auth for first iteration)
    path('api/listings', __import__('api.views', fromlist=['']).listings_geo, name='api_listings_geo'),
    path('api/listings/<int:pk>', __import__('api.views', fromlist=['']).listing_geo_detail, name='api_listing_geo_detail'),
    path('api/openapi.json', __import__('api.views', fromlist=['']).openapi_spec, name='api_openapi_spec'),
    
    # Chatbot API endpoints - AI-friendly read-only endpoints for customer service bots
    path('api/bot/search', __import__('api.chatbot_api', fromlist=['']).chatbot_listings_search, name='chatbot_listings_search'),
    path('api/bot/listing/<int:pk>', __import__('api.chatbot_api', fromlist=['']).chatbot_listing_detail, name='chatbot_listing_detail'),
    path('api/bot/stats', __import__('api.chatbot_api', fromlist=['']).chatbot_listings_stats, name='chatbot_listings_stats'),
    path('api/bot/locations', __import__('api.chatbot_api', fromlist=['']).chatbot_locations, name='chatbot_locations'),
    path('api/bot/docs', __import__('api.chatbot_api', fromlist=['']).chatbot_api_docs, name='chatbot_api_docs'),
    path('api/bot/openapi.json', __import__('api.chatbot_api', fromlist=['']).chatbot_openapi_spec, name='chatbot_openapi_spec'),
    path('api/whatsapp/listing/<int:listing_id>/conversation', __import__('listings.whatsapp', fromlist=['']).listing_conversation, name='whatsapp_listing_conversation'),
    path('api/whatsapp/listing/<int:listing_id>/send', __import__('listings.whatsapp', fromlist=['']).send_listing_message, name='whatsapp_listing_send'),
    path('api/whatsapp/conversations', __import__('listings.whatsapp', fromlist=['']).conversations_index, name='whatsapp_conversations_index'),
    path('api/whatsapp/conversation/<int:conversation_id>/messages', __import__('listings.whatsapp', fromlist=['']).conversation_messages, name='whatsapp_conversation_messages'),
    path('api/whatsapp/conversation/<int:conversation_id>/send', __import__('listings.whatsapp', fromlist=['']).send_conversation_message, name='whatsapp_conversation_send'),
    path('api/whatsapp/listing/<int:listing_id>/suggest', __import__('listings.ai', fromlist=['']).suggest_listing_reply, name='whatsapp_listing_suggest'),
    path('api/whatsapp/webhook', __import__('listings.whatsapp', fromlist=['']).waha_webhook, name='whatsapp_waha_webhook'),
    path('api/investor/medical-rentals/summary', listing_views.investor_medical_rentals_summary, name='investor_medical_rentals_summary'),
    path('listings/airbnb-revenue-heatmap-data/', listing_views.airbnb_revenue_heatmap_data, name='airbnb_revenue_heatmap_data'),
]

if _has_graphql:
    urlpatterns += [path('graphql/', GraphQLView.as_view(graphiql=True))]

if _has_rosetta:
    urlpatterns += [path('rosetta/', include('rosetta.urls'))]

# Prefixed URLs (All user-facing paths)
# All paths within i18n_patterns will automatically have the language prefix (e.g., /en/ or /es/)
# prepended to them.
prefixed_urlpatterns = i18n_patterns(
    path('admin/', admin.site.urls),
    path('baton/', include('baton.urls')),
    #  path('', include('pages.urls')),
    # New frontend demo routes'', include('pages.urls')),
    # N
    path('listings/', include('listings.urls')),
    # Root opens directly on the map experience.
    path('', listing_views.new_map_view, name='home_wizard'),
    path('', listing_views.new_map_view, name='new_index'),
    path('properties/', listing_views.new_properties, name='new_properties'),
    path('properties/page/<int:page>/', listing_views.new_properties, name='new_properties_page'),
    path('opportunities/', listing_views.new_properties, name='opportunities'),
    path('opportunities/under-1.25m/', listing_views.new_properties, {'max_price': '1250000'}, name='opportunities_under'),
    path('opportunities/over-1.25m/', listing_views.new_properties, {'min_price': '1250000'}, name='opportunities_over'),
    # financing/ removed — page still accessible if uncommented later
    # Map page (missing in runtime urls; templates reference 'new_map')
    path('map/', listing_views.new_map_view, name='new_map'),
    path('investor/medical-rentals/', listing_views.investor_medical_rentals, name='investor_medical_rentals'),
    path('maplibre/', listing_views.new_maplibre_view, name='new_maplibre'),
    path('property-details/', listing_views.new_property_details_preview, name='new_property_details'),
    path('listing/<int:listing_id>/', listing_views.new_listing_detail, name='new_listing_detail'),
    path('listing/<int:listing_id>/portfolio/', listing_views.listing_portfolio, name='new_listing_portfolio'),
    path('listing/<int:listing_id>/map/', listing_views.listing_map_embed, name='listing_map_embed'),
    path('listing/<int:listing_id>/map-data/', listing_views.listing_map_data, name='listing_map_data'),
    # contact/ removed — page still accessible if uncommented later
    path('map-copy/', listing_views.new_map_view_copy, name='new_map_copy'),
    path('map-simplified/', xframe_options_exempt(TemplateView.as_view(template_name='newfrontend/mapstandalone/simplified/index.html')), name='new_map_simplified'),
    path('whatsapp-inbox/', listing_views.whatsapp_inbox, name='whatsapp_inbox'),
    # Project showcase page for client presentation
    path('project-showcase/', TemplateView.as_view(template_name='newfrontend/project-showcase.html'), name='project_showcase'),
    path('proje-vitrini/', TemplateView.as_view(template_name='newfrontend/project-showcase-tr.html'), name='project_showcase_tr'),
    # 404 preview route so you can check the page without toggling DEBUG
    path('404-preview/', TemplateView.as_view(template_name='newfrontend/page-404.html'), name='new_404_preview'),
    # Include distill URL patterns so static generation covers all languages
    *distill.urlpatterns,
)

# Combine non-prefixed and prefixed URLs
urlpatterns += prefixed_urlpatterns

# Static and Debug Toolbar URLs remain outside i18n_patterns
urlpatterns += static(settings.MEDIA_URL,document_root=settings.MEDIA_ROOT)

# Distill URL patterns are included inside i18n_patterns above for per-language output

# Django Debug Toolbar (only if installed and debug)
if settings.DEBUG and 'debug_toolbar' in settings.INSTALLED_APPS:
    import debug_toolbar
    urlpatterns += [
        path('__debug__/', include(debug_toolbar.urls)),
    ]

# Custom error handlers
handler404 = 'pages.views.custom_404'

"""
    path('accounts/', include('accounts.urls')),
    path('contacts/', include('contacts.urls')),
    path('AgesVerification/', include('Ages.urls')),
    path('blog/', include('blog.urls')),
"""
