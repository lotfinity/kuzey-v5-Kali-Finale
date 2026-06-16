from django_distill import distill_path
from django.views.generic import TemplateView
from listings import views as listing_views
from pages import views as pages_views
from listings.models import Listing

PER_PAGE = 6

def get_all_listing_ids():
    # Return a list of dictionaries, one for each listing
    # The key, 'listing_id', matches the name of the parameter in the URL
    return [{'listing_id': listing.id} for listing in Listing.objects.filter(is_published=True)]

# The list of URLs to distill
urlpatterns = [
    # Root index: redirect to English new homepage for static hosting
    distill_path('',
                 TemplateView.as_view(template_name='newfrontend/root_index.html'),
                 name='root_index'),
    distill_path('new/',
                 listing_views.home_wizard,
                 name='new_index'),
    distill_path('new/opportunities/',
                 listing_views.new_properties,
                 name='opportunities'),
    distill_path('new/opportunities/under-1.25m/',
                 listing_views.new_properties,
                 kwargs={'max_price': '1250000'},
                 name='opportunities_under'),
    distill_path('new/opportunities/over-1.25m/',
                 listing_views.new_properties,
                 kwargs={'min_price': '1250000'},
                 name='opportunities_over'),
    distill_path('new/properties/',
                 listing_views.new_properties,
                 name='new_properties'),
    # Additional paginated static pages: /new/properties/page/<n>/
    distill_path('new/properties/page/<int:page>/',
                 listing_views.new_properties,
                 name='new_properties_page',
                 distill_func=lambda: (
                     [{'page': p} for p in range(2, max(2, (Listing.objects.filter(is_published=True).count() - 1) // PER_PAGE + 2))]
                 )),
    distill_path('new/financing/',
                 pages_views.financing,
                 name='new_financing'),
    distill_path('new/property-details/',
                 listing_views.new_property_details_preview,
                 name='new_property_details'),
    distill_path('new/listing/<int:listing_id>/',
                 listing_views.new_listing_detail,
                 name='new_listing_detail',
                 distill_func=get_all_listing_ids),
    distill_path('new/contact/',
                 TemplateView.as_view(template_name='newfrontend/contact.html'),
                 name='new_contact'),
    distill_path('new/map/',
                 listing_views.new_map_view,
                 name='new_map'),
    # Include the map copy and simplified standalone map in static build
    distill_path('new/map-copy/',
                 listing_views.new_map_view_copy,
                 name='new_map_copy'),
    distill_path('new/map-simplified/',
                 TemplateView.as_view(template_name='newfrontend/mapstandalone/simplified/index.html'),
                 name='new_map_simplified'),
    # Generate static JSON for map data so the map works on the static site
    distill_path('listings/map-data/',
                 listing_views.map_data,
                 name='listings_map_data'),
    distill_path('new/404-preview/',
                 TemplateView.as_view(template_name='newfrontend/page-404.html'),
                 name='new_404_preview'),
]
