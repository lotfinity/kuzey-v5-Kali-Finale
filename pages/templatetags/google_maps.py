from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode

from django import template


register = template.Library()


def _coordinate(value, minimum, maximum):
    """Return a normalized coordinate string, or ``None`` when invalid."""
    try:
        coordinate = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None

    if coordinate < Decimal(str(minimum)) or coordinate > Decimal(str(maximum)):
        return None

    return format(coordinate, "f")


def _coordinates(latitude, longitude):
    latitude_value = _coordinate(latitude, -90, 90)
    longitude_value = _coordinate(longitude, -180, 180)
    if latitude_value is None or longitude_value is None:
        return None
    return "{},{}".format(latitude_value, longitude_value)


@register.simple_tag
def google_maps_url(latitude, longitude, mode="place"):
    """Build a public Google Maps place or directions URL from coordinates."""
    coordinates = _coordinates(latitude, longitude)
    if not coordinates:
        return ""

    if mode == "directions":
        query = urlencode({"api": 1, "destination": coordinates})
        return "https://www.google.com/maps/dir/?{}".format(query)

    query = urlencode({"api": 1, "query": coordinates})
    return "https://www.google.com/maps/search/?{}".format(query)


@register.simple_tag
def google_maps_embed_url(latitude, longitude, zoom=16, language="en"):
    """Build a lightweight iframe URL without an opaque Google ``pb`` value."""
    coordinates = _coordinates(latitude, longitude)
    if not coordinates:
        return ""

    try:
        zoom_value = max(0, min(21, int(zoom)))
    except (TypeError, ValueError):
        zoom_value = 16

    query = urlencode(
        {
            "q": coordinates,
            "z": zoom_value,
            "hl": language or "en",
            "output": "embed",
        }
    )
    return "https://www.google.com/maps?{}".format(query)
