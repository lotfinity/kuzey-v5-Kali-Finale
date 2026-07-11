from django.urls import path
from . import views

app_name = 'listings'

urlpatterns = [
    path('', views.index , name='listings'),
    path('<int:listing_id>/portfolio/', views.listing_portfolio, name='listing_portfolio'),
    path('<int:listing_id>/',views.listing , name='listing'),
    path('search/',views.search , name='search'),
    path('map/', views.map_view, name='map'),
    path('map-data/', views.map_data, name='map_data'),
    path('airbnb-map-data/', views.airbnb_map_data, name='airbnb_map_data'),
    path('airbnb-revenue-heatmap-data/', views.airbnb_revenue_heatmap_data, name='airbnb_revenue_heatmap_data'),

]
