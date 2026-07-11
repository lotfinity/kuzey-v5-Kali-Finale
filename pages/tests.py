from django.test import SimpleTestCase

from pages.templatetags.google_maps import google_maps_embed_url, google_maps_url


class GoogleMapsTemplateTagTests(SimpleTestCase):
    def test_place_url_uses_coordinates(self):
        url = google_maps_url(41.026688, 28.625306)

        self.assertEqual(
            url,
            "https://www.google.com/maps/search/?api=1&query=41.026688%2C28.625306",
        )

    def test_directions_url_uses_destination(self):
        url = google_maps_url(41.026688, 28.625306, "directions")

        self.assertEqual(
            url,
            "https://www.google.com/maps/dir/?api=1&destination=41.026688%2C28.625306",
        )

    def test_embed_url_is_readable_and_clamps_zoom(self):
        url = google_maps_embed_url(41.026688, 28.625306, 99, "tr")

        self.assertEqual(
            url,
            "https://www.google.com/maps?q=41.026688%2C28.625306&z=21&hl=tr&output=embed",
        )

    def test_invalid_coordinates_return_empty_string(self):
        self.assertEqual(google_maps_url(200, 28.625306), "")
        self.assertEqual(google_maps_embed_url(41.026688, "not-a-number"), "")
