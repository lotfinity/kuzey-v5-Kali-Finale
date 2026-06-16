from django.db import models
from datetime import datetime
from django.utils.timezone import timezone
from django.utils import timezone as django_timezone
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut, GeocoderServiceError
import time

from realtors.models import Realtor
from django.utils.translation import gettext_lazy as _
import os

from .choices import rentability_group_badges, rentability_group_choices

# Create your models here.


class CurrencySettings(models.Model):
    try_to_usd = models.DecimalField(
        max_digits=12,
        decimal_places=6,
        default=0.021661,
        verbose_name=_('1 TL in USD'),
    )
    try_to_eur = models.DecimalField(
        max_digits=12,
        decimal_places=6,
        default=0.018768,
        verbose_name=_('1 TL in EUR'),
    )
    try_to_dzd = models.DecimalField(
        max_digits=12,
        decimal_places=6,
        default=5,
        verbose_name=_('1 TL in DZD'),
        help_text=_('Default business rate: 100 TL = 500 DZD.'),
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('Currency settings')
        verbose_name_plural = _('Currency settings')

    def __str__(self):
        return _('Currency settings')

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

class Listing(models.Model):
    realtor = models.ForeignKey(Realtor, on_delete=models.DO_NOTHING, blank=True)
    title = models.CharField(max_length=200)
    address = models.CharField(max_length=200)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    zipcode = models.CharField(max_length=20)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    description = models.TextField(blank=True)
    price = models.IntegerField()
    bedrooms = models.CharField(max_length=20, blank=True, default='')
    # Deal type: strictly 'Kiralık' or 'Satış'
    DEAL_TYPE_CHOICES = (
        ('kiralik', _('Kiralık')),
        ('satis', _('Satış')),
    )
    deal_type = models.CharField(
        max_length=10,
        choices=DEAL_TYPE_CHOICES,
        default='satis',
        blank=False,
        db_index=True,
        verbose_name=_('Deal type'),
    )
    # Real estate type (e.g., Apartment/Daire, Villa, etc.)
    property_type = models.CharField(max_length=50, blank=True)
    bathrooms = models.IntegerField()
    garage = models.IntegerField(default=0)
    sqft = models.IntegerField()
    lot_size = models.DecimalField(max_digits=6, decimal_places=1, default=0.0)
    # New reference fields from source
    external_id = models.CharField(max_length=64, blank=True, db_index=True)
    phone = models.CharField(max_length=32, blank=True, db_index=True)
    ad_date = models.DateField(null=True, blank=True)
    # Source page URL from which this listing was scraped
    original_url = models.URLField(max_length=500, blank=True)
    # Details
    m2_gross = models.IntegerField(null=True, blank=True)
    m2_net = models.IntegerField(null=True, blank=True)
    rooms_text = models.CharField(max_length=20, blank=True)
    building_age = models.IntegerField(null=True, blank=True)
    floor_number = models.IntegerField(null=True, blank=True)
    floors_total = models.IntegerField(null=True, blank=True)
    heating = models.CharField(max_length=100, blank=True)
    kitchen_type = models.CharField(max_length=100, blank=True)
    balcony = models.CharField(max_length=100, blank=True)
    elevator = models.BooleanField(null=True, blank=True)
    parking_area = models.CharField(max_length=100, blank=True)
    furnished = models.BooleanField(null=True, blank=True)
    usage_status = models.CharField(max_length=100, blank=True)
    in_complex = models.BooleanField(null=True, blank=True)
    complex_name = models.CharField(max_length=150, blank=True)
    maintenance_fee = models.IntegerField(null=True, blank=True)
    deposit = models.IntegerField(null=True, blank=True)
    deed_status = models.CharField(max_length=100, blank=True)
    from_whom = models.CharField(max_length=100, blank=True)
    rentability_groups = models.CharField(
        max_length=255,
        blank=True,
        default='',
        db_index=True,
        verbose_name=_('Rentability groups'),
        help_text=_('Tenant/renter groups this apartment is a strong match for.'),
    )
    is_published = models.BooleanField(default=True)
    list_date = models.DateTimeField(default=datetime.now, blank=True)
    estimated_monthly_rent_try = models.IntegerField(null=True, blank=True, db_index=True)
    rent_estimate_source = models.CharField(max_length=80, blank=True)
    rent_estimate_updated_at = models.DateTimeField(null=True, blank=True)
    airbnb_comp_count = models.PositiveIntegerField(default=0)
    airbnb_comp_median_try = models.IntegerField(null=True, blank=True)
    source_batch_label = models.CharField(max_length=120, blank=True, db_index=True)
    source_search_context = models.JSONField(default=dict, blank=True)

    def geocode_address(self):
        """Geocode the address using Nominatim. Skips if coordinates already set."""
        # If we already have coordinates, don't overwrite them
        if self.latitude is not None and self.longitude is not None:
            return
        if not any([self.address, self.city, self.state]):
            return
            
        # Construct the full address
        address_parts = [
            self.address,
            self.city,
            self.state,
            self.zipcode
        ]
        full_address = ", ".join(filter(None, address_parts))
        
        try:
            geolocator = Nominatim(user_agent="coralcity_property")
            location = geolocator.geocode(full_address)
            if location:
                self.latitude = location.latitude
                self.longitude = location.longitude
                # Don't save here - it will be saved in save() method
        except (GeocoderTimedOut, GeocoderServiceError):
            # If geocoding fails, we'll just leave coordinates as they are
            pass

    def save(self, *args, **kwargs):
        # Allow callers to skip geocoding (used by importers or deferred workflows)
        skip_geocode = kwargs.pop("skip_geocode", False)
        # Only geocode when we don't already have coordinates and the address changed/adding
        should_geocode = False
        if self.latitude is None or self.longitude is None:
            if self._state.adding:
                should_geocode = True
            elif getattr(self, '_address_changed', False):
                should_geocode = True
        if should_geocode and not skip_geocode:
            self.geocode_address()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.title

    @property
    def price_trend(self):
        return 'up' if self.pk % 2 == 0 else 'down'

    @property
    def trend_percent(self):
        return 1 + ((self.pk or 0) % 11)

    @property
    def is_hot(self):
        return self.pk % 3 == 0

    @property
    def is_new(self):
        return self.pk % 3 == 1

    @property
    def estimated_rent(self):
        if self.estimated_monthly_rent_try:
            return self.estimated_monthly_rent_try
        return (self.price // 65) + ((self.pk or 0) % 7) * 100

    @property
    def rentability(self):
        return 85 + ((self.pk or 0) % 15)

    @property
    def rentability_group_values(self):
        return [value for value in self.rentability_groups.split(',') if value]

    @property
    def rentability_group_labels(self):
        return [
            rentability_group_choices.get(value, value.replace('_', ' ').title())
            for value in self.rentability_group_values
        ]

    @property
    def rentability_group_badges(self):
        return [
            {
                'value': value,
                'label': rentability_group_choices.get(value, value.replace('_', ' ').title()),
                'badge': rentability_group_badges.get(value),
            }
            for value in self.rentability_group_values[:5]
            if rentability_group_badges.get(value)
        ]


class AirbnbListing(models.Model):
    listing_id = models.CharField(max_length=40, unique=True, db_index=True)
    title = models.CharField(max_length=255, blank=True)
    tagline = models.CharField(max_length=255, blank=True)
    property_type = models.CharField(max_length=120, blank=True)
    listing_url = models.URLField(max_length=500, blank=True)
    booking_url = models.URLField(max_length=700, blank=True)

    city = models.CharField(max_length=160, blank=True)
    full_address = models.CharField(max_length=300, blank=True)
    location = models.CharField(max_length=300, blank=True)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)

    bedroom_count = models.PositiveSmallIntegerField(null=True, blank=True)
    bathroom_count = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    bed_count = models.PositiveSmallIntegerField(null=True, blank=True)
    guest_capacity = models.PositiveSmallIntegerField(null=True, blank=True)

    photos = models.JSONField(default=list, blank=True)
    highlights = models.JSONField(default=list, blank=True)
    amenity_ids = models.JSONField(default=list, blank=True)

    host_id = models.CharField(max_length=40, blank=True)
    host_name = models.CharField(max_length=160, blank=True)
    host_avatar = models.URLField(max_length=700, blank=True)
    is_superhost = models.BooleanField(default=False)
    is_verified = models.BooleanField(null=True, blank=True)
    host_rating = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    host_review_count = models.PositiveIntegerField(null=True, blank=True)
    years_hosting = models.PositiveSmallIntegerField(null=True, blank=True)

    overall_rating = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True)
    review_count = models.PositiveIntegerField(null=True, blank=True)
    rating_categories = models.JSONField(default=list, blank=True)
    is_guest_favorite = models.BooleanField(null=True, blank=True)

    nightly_rate = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=8, blank=True)
    total_cost = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    pricing = models.JSONField(default=dict, blank=True)

    cancellation_policy = models.CharField(max_length=160, blank=True)
    cancellation_terms = models.JSONField(default=list, blank=True)
    is_rare_find = models.BooleanField(default=False)
    is_available = models.BooleanField(null=True, blank=True)
    unavailability_reason = models.CharField(max_length=255, blank=True)
    rank = models.PositiveIntegerField(null=True, blank=True, db_index=True)

    source_destination_query = models.CharField(max_length=255, blank=True, db_index=True)
    search_adult_guests = models.PositiveSmallIntegerField(null=True, blank=True)
    search_page_number = models.PositiveIntegerField(null=True, blank=True)
    raw_search_payload = models.JSONField(default=dict, blank=True)
    raw_details_payload = models.JSONField(default=dict, blank=True)
    scraped_at = models.DateTimeField(default=django_timezone.now, db_index=True)
    details_scraped_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('rank', '-overall_rating', 'title')
        verbose_name = _('Airbnb listing')
        verbose_name_plural = _('Airbnb listings')

    def __str__(self):
        return self.title or self.listing_id


class ListingPhoneEntry(models.Model):
    STATUS_OK = 'ok'
    STATUS_MISSING = 'missing'
    STATUS_ERROR = 'error'
    STATUS_SKIPPED = 'skipped'
    STATUS_CHOICES = (
        (STATUS_OK, _('OK')),
        (STATUS_MISSING, _('Missing')),
        (STATUS_ERROR, _('Error')),
        (STATUS_SKIPPED, _('Skipped')),
    )

    listing = models.ForeignKey(
        Listing,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='phone_entries',
    )
    external_id = models.CharField(max_length=64, db_index=True)
    phone_normalized = models.CharField(max_length=32, blank=True, db_index=True)
    phone_raw = models.CharField(max_length=64, blank=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=STATUS_MISSING, db_index=True)
    source = models.CharField(max_length=80, default='android_visible_index', db_index=True)
    source_result_path = models.CharField(max_length=500, blank=True)
    debug_folder = models.CharField(max_length=500, blank=True)
    error = models.TextField(blank=True)
    scraped_at = models.DateTimeField(default=django_timezone.now, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('external_id', 'source')
        ordering = ('-scraped_at', '-updated_at')

    def __str__(self):
        return '%s %s' % (self.external_id, self.phone_normalized or self.status)


class WhatsAppConversation(models.Model):
    listing = models.ForeignKey(
        Listing,
        on_delete=models.CASCADE,
        related_name='whatsapp_conversations',
    )
    chat_id = models.CharField(max_length=120, db_index=True)
    phone_number = models.CharField(max_length=32, db_index=True)
    display_name = models.CharField(max_length=160, blank=True)
    session = models.CharField(max_length=80, blank=True, db_index=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('listing', 'chat_id', 'session')
        ordering = ('-updated_at',)

    def __str__(self):
        return '%s - %s' % (self.listing, self.chat_id)


class WhatsAppIdentityAlias(models.Model):
    conversation = models.ForeignKey(
        WhatsAppConversation,
        on_delete=models.CASCADE,
        related_name='identity_aliases',
    )
    session = models.CharField(max_length=80, blank=True, db_index=True)
    alias = models.CharField(max_length=160, db_index=True)
    canonical_id = models.CharField(max_length=160, blank=True, db_index=True)
    phone_number = models.CharField(max_length=32, blank=True, db_index=True)
    source = models.CharField(max_length=40, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('session', 'alias')
        ordering = ('alias',)

    def __str__(self):
        return '%s -> %s' % (self.alias, self.conversation_id)


class WhatsAppMessage(models.Model):
    DIRECTION_IN = 'in'
    DIRECTION_OUT = 'out'
    DIRECTION_CHOICES = (
        (DIRECTION_IN, _('Incoming')),
        (DIRECTION_OUT, _('Outgoing')),
    )

    conversation = models.ForeignKey(
        WhatsAppConversation,
        on_delete=models.CASCADE,
        related_name='messages',
    )
    waha_message_id = models.CharField(max_length=255, blank=True, db_index=True)
    direction = models.CharField(max_length=8, choices=DIRECTION_CHOICES, db_index=True)
    sender = models.CharField(max_length=120, blank=True)
    body = models.TextField(blank=True)
    message_type = models.CharField(max_length=40, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True, db_index=True)
    raw_payload = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('sent_at', 'id')

    def __str__(self):
        return '%s %s' % (self.direction, self.waha_message_id or self.pk)


def listing_image_upload_to(instance, filename):
    listing = getattr(instance, 'listing', None)
    # Use external_id if present; otherwise fallback to DB pk
    folder_key = None
    if listing is not None:
        folder_key = listing.external_id or (str(listing.pk) if listing.pk else None)
    folder_key = folder_key or 'unknown'
    # Keep original filename base to avoid collisions per listing
    name, ext = os.path.splitext(filename)
    safe_name = (name or 'image').replace('/', '_').replace('\\', '_')
    return f"photos/listing_{folder_key}/{safe_name}{ext or '.jpg'}"


class ListingImage(models.Model):
    listing = models.ForeignKey(
        Listing, on_delete=models.CASCADE, related_name="images"
    )
    image = models.ImageField(upload_to=listing_image_upload_to, blank=True)
    title = models.CharField(max_length=255, blank=True)
    order = models.PositiveIntegerField(default=0)
    is_primary = models.BooleanField(default=False)
    is_visible = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    # Optional manual crop box (pixels) applied on save if set
    crop_x = models.PositiveIntegerField(null=True, blank=True)
    crop_y = models.PositiveIntegerField(null=True, blank=True)
    crop_width = models.PositiveIntegerField(null=True, blank=True)
    crop_height = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["order", "created_at"]

    def __str__(self):
        return f"Image for {self.listing_id} - {self.title or 'Untitled'}"

    def save(self, *args, **kwargs):
        if self.is_primary:
            ListingImage.objects.filter(listing=self.listing, is_primary=True).exclude(
                pk=self.pk
            ).update(is_primary=False)

        # If a crop is requested, attempt to crop using Pillow before saving
        did_crop = False
        try:
            if self.image and all([
                self.crop_x is not None,
                self.crop_y is not None,
                self.crop_width is not None,
                self.crop_height is not None,
            ]):
                from PIL import Image
                import os
                img_path = self.image.path
                with Image.open(img_path) as im:
                    x = int(self.crop_x or 0)
                    y = int(self.crop_y or 0)
                    w = int(self.crop_width or 0)
                    h = int(self.crop_height or 0)
                    if w > 0 and h > 0:
                        # Clamp crop box within image bounds
                        W, H = im.size
                        x = max(0, min(x, W - 1))
                        y = max(0, min(y, H - 1))
                        w = max(1, min(w, W - x))
                        h = max(1, min(h, H - y))
                        box = (x, y, x + w, y + h)
                        im_cropped = im.crop(box)
                        # Overwrite original file
                        im_cropped.save(img_path)
                        did_crop = True
        except Exception:
            pass

        # Clear crop fields after successful crop to avoid re-cropping on next save
        if did_crop:
            self.crop_x = self.crop_y = self.crop_width = self.crop_height = None

        super().save(*args, **kwargs)


    # Convenience property to filter visible images from templates via listing.visible_images
    @property
    def is_croppable(self):
        return all([
            self.crop_x is not None,
            self.crop_y is not None,
            self.crop_width is not None,
            self.crop_height is not None,
        ])


def _listing_visible_images(self):
    return self.images.filter(is_visible=True).order_by('order', 'id')

Listing.visible_images = property(_listing_visible_images)


class ListingImportJob(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('running', 'Running'),
        ('success', 'Success'),
        ('failed', 'Failed'),
    ]

    realtor = models.ForeignKey(Realtor, on_delete=models.PROTECT, related_name='import_jobs', verbose_name=_('Realtor'))
    # Either provide a single URL or a CSV file; if both, CSV wins
    single_url = models.URLField(blank=True, verbose_name=_('Single URL'))
    csv_file = models.FileField(upload_to='admin_imports/', blank=True, verbose_name=_('CSV file'))
    cookie_file = models.FileField(upload_to='admin_imports/', blank=True, verbose_name=_('Cookie file'))

    # Options
    delay = models.FloatField(default=2.0, verbose_name=_('Delay (seconds)'))
    debug = models.BooleanField(default=False, verbose_name=_('Debug'))
    skip_geocode = models.BooleanField(default=False, verbose_name=_('Skip geocoding'))
    headed = models.BooleanField(default=False, verbose_name=_('Headed (show browser)'))
    no_images = models.BooleanField(default=False, verbose_name=_('No images'))
    images_max = models.PositiveIntegerField(default=15, verbose_name=_('Max images'))

    # Execution bookkeeping
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='pending', db_index=True, verbose_name=_('Status'))
    log = models.TextField(blank=True, verbose_name=_('Log'))
    created_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='listing_import_jobs', verbose_name=_('Created by'))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_('Created at'))
    started_at = models.DateTimeField(null=True, blank=True, verbose_name=_('Started at'))
    finished_at = models.DateTimeField(null=True, blank=True, verbose_name=_('Finished at'))

    # Cache of the CSV path that was used (for audit/debug)
    csv_path_cached = models.CharField(max_length=500, blank=True, verbose_name=_('CSV path (cached)'))

    class Meta:
        ordering = ['-created_at']
        verbose_name = _('Listing import job')
        verbose_name_plural = _('Listing import jobs')

    def __str__(self):
        return f"Import Job #{self.pk or 'new'} for {getattr(self.realtor, 'name', 'realtor')}"
