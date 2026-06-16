from django.contrib import admin
from django.utils.html import format_html
from django.db import models
from django import forms
from import_export.admin import ImportExportModelAdmin
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.management import call_command
from .models import AirbnbListing, CurrencySettings, Listing, ListingImage, ListingImportJob, ListingPhoneEntry, WhatsAppConversation, WhatsAppIdentityAlias, WhatsAppMessage
from .importer import start_import_job_async
from django.shortcuts import render, redirect
from django.http import JsonResponse, Http404
from django.urls import path, reverse
from django.core.files.base import ContentFile
import base64
try:
    from django.contrib.admin.helpers import ACTION_CHECKBOX_NAME
except Exception:
    ACTION_CHECKBOX_NAME = '_selected_action'
from imagetools.forms import BulkImageEditForm, LogoWatermarkForm
from imagetools.utils import process_image, add_corner_triangle_to_file, add_logo_watermark_to_file
from .choices import rentability_group_choices

# Optional: django-image-uploader-widget integration (nice preview/replace UI)
try:
    from image_uploader_widget.widgets import ImageUploaderWidget  # type: ignore
    HAS_IMAGE_UPLOADER = True
except Exception:
    ImageUploaderWidget = None  # type: ignore
    HAS_IMAGE_UPLOADER = False


if HAS_IMAGE_UPLOADER:
    class ListingImageForm(forms.ModelForm):
        class Meta:
            model = ListingImage
            fields = '__all__'
            widgets = {
                'image': ImageUploaderWidget(),
            }
else:
    class ListingImageForm(forms.ModelForm):  # fallback default form
        class Meta:
            model = ListingImage
            fields = '__all__'


class ListingAdminForm(forms.ModelForm):
    rentability_groups = forms.MultipleChoiceField(
        choices=rentability_group_choices.items(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label=_('Rentability groups'),
        help_text=_('Select every renter profile this apartment fits.'),
    )

    class Meta:
        model = Listing
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.initial['rentability_groups'] = self.instance.rentability_group_values

    def clean_rentability_groups(self):
        return ','.join(self.cleaned_data.get('rentability_groups') or [])


class RentabilityGroupFilter(admin.SimpleListFilter):
    title = _('Rentability group')
    parameter_name = 'rentability_group'

    def lookups(self, request, model_admin):
        return tuple(rentability_group_choices.items())

    def queryset(self, request, queryset):
        value = self.value()
        if value:
            return queryset.filter(rentability_groups__contains=value)
        return queryset

class ListingImageInline(admin.TabularInline):
    model = ListingImage
    extra = 0
    form = ListingImageForm
    fields = (
        'preview', 'title', 'order', 'is_primary', 'is_visible', 'image',
    )
    readonly_fields = ('preview',)
    ordering = ('order', 'id')
    extra = 0
    show_change_link = True

    def preview(self, obj):
        if getattr(obj, 'image', None):
            try:
                from easy_thumbnails.files import get_thumbnailer
                thumb = get_thumbnailer(obj.image).get_thumbnail({'size': (160, 100), 'crop': True})
                return format_html('<img src="{}" style="max-width:160px; height:auto; border-radius:6px;"/>', thumb.url)
            except Exception:
                try:
                    return format_html('<img src="{}" style="max-width:160px; height:auto; border-radius:6px;"/>', obj.image.url)
                except Exception:
                    return ""
        return ""
    preview.short_description = _("Preview")


class ListingAdmin(ImportExportModelAdmin):
    form = ListingAdminForm
    list_display = (
        'id', 'title', 'is_published', 'deal_type_label', 'price', 'list_date', 'realtor',
        'rentability_groups_label', 'external_id', 'original_url_link'
    )
    list_display_links = ('id' , 'title')
    list_filter = ('realtor', 'city', 'state', RentabilityGroupFilter)
    list_editable = ('is_published',)
    search_fields = (
        'title','description','address','city','state','zipcode','price',
        'external_id','original_url','rentability_groups'
    )
    list_per_page = 15
    inlines = [ListingImageInline]
    actions = ['delete_all_images']

    def deal_type_label(self, obj):
        try:
            return obj.get_deal_type_display()
        except Exception:
            return getattr(obj, 'deal_type', '')
    deal_type_label.short_description = _('Deal type')
    deal_type_label.admin_order_field = 'deal_type'

    def rentability_groups_label(self, obj):
        labels = obj.rentability_group_labels
        return ', '.join(labels) if labels else '-'
    rentability_groups_label.short_description = _('Rentability groups')
    rentability_groups_label.admin_order_field = 'rentability_groups'

    def delete_all_images(self, request, queryset):
        total = 0
        for listing in queryset:
            qs = listing.images.all()
            count = qs.count()
            if count:
                qs.delete()
                total += count
        self.message_user(request, _('%d images deleted from selected listings') % total)
    delete_all_images.short_description = _('Delete all images for selected listings')

    def original_url_link(self, obj):
        url = getattr(obj, 'original_url', '') or ''
        if not url:
            return ''
        try:
            return format_html('<a href="{}" target="_blank" rel="noopener noreferrer">{}</a>', url, _("Source"))
        except Exception:
            return url
    original_url_link.short_description = _('Original URL')


# Register your models here.
admin.site.register(Listing , ListingAdmin)


@admin.register(CurrencySettings)
class CurrencySettingsAdmin(admin.ModelAdmin):
    list_display = ('try_to_usd', 'try_to_eur', 'try_to_dzd', 'updated_at')
    fieldsets = (
        (_('Manual exchange rates'), {
            'fields': ('try_to_usd', 'try_to_eur', 'try_to_dzd'),
            'description': _('Rates are stored as the value of 1 Turkish Lira in the target currency. DZD defaults to 1 TL = 5 DZD.'),
        }),
    )

    def has_add_permission(self, request):
        return not CurrencySettings.objects.exists()


@admin.register(AirbnbListing)
class AirbnbListingAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'listing_id', 'title', 'property_type', 'nightly_rate', 'currency',
        'overall_rating', 'review_count', 'rank', 'source_destination_query', 'scraped_at',
    )
    list_filter = (
        'source_destination_query', 'property_type', 'currency', 'is_superhost',
        'is_guest_favorite', 'is_available', 'scraped_at',
    )
    search_fields = (
        'listing_id', 'title', 'tagline', 'property_type', 'city', 'full_address',
        'location', 'host_name', 'listing_url',
    )
    readonly_fields = ('created_at', 'updated_at', 'scraped_at', 'details_scraped_at')
    ordering = ('rank', '-overall_rating', 'title')

    def has_add_permission(self, request):
        return False


@admin.register(ListingPhoneEntry)
class ListingPhoneEntryAdmin(admin.ModelAdmin):
    list_display = (
        'id', 'external_id', 'listing', 'phone_normalized', 'status', 'source', 'scraped_at', 'updated_at',
    )
    list_filter = ('status', 'source', 'scraped_at', 'updated_at')
    search_fields = ('external_id', 'phone_normalized', 'phone_raw', 'listing__title', 'error')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(WhatsAppConversation)
class WhatsAppConversationAdmin(admin.ModelAdmin):
    list_display = ('id', 'listing', 'display_name', 'phone_number', 'chat_id', 'session', 'last_synced_at', 'updated_at')
    list_filter = ('session', 'updated_at')
    search_fields = ('listing__title', 'phone_number', 'chat_id', 'display_name')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(WhatsAppIdentityAlias)
class WhatsAppIdentityAliasAdmin(admin.ModelAdmin):
    list_display = ('id', 'conversation', 'alias', 'canonical_id', 'phone_number', 'session', 'source', 'updated_at')
    list_filter = ('session', 'source', 'updated_at')
    search_fields = ('alias', 'canonical_id', 'phone_number', 'conversation__chat_id', 'conversation__listing__title')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(WhatsAppMessage)
class WhatsAppMessageAdmin(admin.ModelAdmin):
    list_display = ('id', 'conversation', 'direction', 'message_type', 'short_body', 'sent_at', 'created_at')
    list_filter = ('direction', 'message_type', 'sent_at')
    search_fields = ('body', 'waha_message_id', 'sender', 'conversation__chat_id', 'conversation__listing__title')
    readonly_fields = ('created_at',)

    def short_body(self, obj):
        body = (obj.body or '').replace('\n', ' ').strip()
        return body[:80] + ('...' if len(body) > 80 else '')
    short_body.short_description = _('Message')


 

@admin.register(ListingImage)
class ListingImageAdmin(admin.ModelAdmin):
    list_display = ('id', 'listing', 'title', 'order', 'is_primary', 'is_visible', 'created_at', 'edit_in_editor')
    list_filter = ('listing', 'is_primary', 'is_visible')
    search_fields = ('title', 'listing__title', 'listing__id')
    ordering = ('listing', 'order', 'id')
    actions = ['make_visible', 'make_hidden', 'bulk_edit_images', 'cover_old_logo', 'apply_logo_watermark', 'apply_logo_watermark_oneclick']

    # Custom URLs for JS editor
    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path('<int:pk>/edit/', self.admin_site.admin_view(self.edit_image_view), name='listings_listingimage_edit'),
            path('<int:pk>/edit/fie/', self.admin_site.admin_view(self.edit_image_view_fie), name='listings_listingimage_edit_fie'),
            path('<int:pk>/edit/save/', self.admin_site.admin_view(self.edit_image_save_view), name='listings_listingimage_edit_save'),
        ]
        return custom + urls

    # Shared helpers for logo watermarking
    def _resolve_logo_path(self):
        from django.conf import settings
        import os
        return os.path.join(getattr(settings, 'BASE_DIR', ''), 'coralcity', 'static', 'listings.png')

    def _apply_logo_batch(self, queryset, logo_path, pos, opacity, scale, margin):
        ok = fail = 0
        for img in queryset.select_related('listing'):
            try:
                if not getattr(img, 'image', None):
                    continue
                add_logo_watermark_to_file(
                    img.image.path,
                    logo_path,
                    position=pos,
                    opacity=opacity,
                    scale=scale,
                    margin_px=margin,
                )
                try:
                    from easy_thumbnails.files import get_thumbnailer
                    get_thumbnailer(img.image).delete_thumbnails()
                except Exception:
                    pass
                ok += 1
            except Exception:
                fail += 1
        return ok, fail

    def edit_in_editor(self, obj):
        try:
            url1 = reverse('admin:listings_listingimage_edit', args=[obj.pk])
            url2 = reverse('admin:listings_listingimage_edit_fie', args=[obj.pk])
            return format_html('<a class="button" href="{}">Toast UI</a> &nbsp; <a class="button" href="{}">Filerobot</a>', url1, url2)
        except Exception:
            return ''
    edit_in_editor.short_description = _('Editor')

    def edit_image_view(self, request, pk):
        obj = self.get_object(request, pk)
        if obj is None:
            raise Http404
        img_url = ''
        try:
            img_url = obj.image.url
        except Exception:
            pass
        ctx = {
            'opts': self.model._meta,
            'obj': obj,
            'image_url': img_url,
            'save_url': reverse('admin:listings_listingimage_edit_save', args=[obj.pk]),
            'cancel_url': reverse('admin:listings_listingimage_change', args=[obj.pk]),
        }
        return render(request, 'admin/listings/image_editor.html', ctx)

    def edit_image_view_fie(self, request, pk):
        obj = self.get_object(request, pk)
        if obj is None:
            raise Http404
        img_url = ''
        try:
            img_url = obj.image.url
        except Exception:
            pass
        ctx = {
            'opts': self.model._meta,
            'obj': obj,
            'image_url': img_url,
            'save_url': reverse('admin:listings_listingimage_edit_save', args=[obj.pk]),
            'cancel_url': reverse('admin:listings_listingimage_change', args=[obj.pk]),
        }
        return render(request, 'admin/listings/image_editor_fie.html', ctx)

    def _save_from_dataurl(self, dataurl) -> bytes:
        # dataurl like 'data:image/png;base64,.....'
        try:
            header, b64 = dataurl.split(',', 1)
            return base64.b64decode(b64)
        except Exception:
            return b''

    def edit_image_save_view(self, request, pk):
        if request.method != 'POST':
            return JsonResponse({'ok': False, 'error': 'POST required'}, status=405)
        obj = self.get_object(request, pk)
        if obj is None:
            return JsonResponse({'ok': False, 'error': 'Not found'}, status=404)

        # Prefer file upload; fallback to dataURL
        content = None
        filename = None
        if 'image' in request.FILES:
            f = request.FILES['image']
            content = f.read()
            filename = f.name
        else:
            dataurl = request.POST.get('dataurl')
            if dataurl:
                content = self._save_from_dataurl(dataurl)
                filename = (obj.image.name.rsplit('/', 1)[-1] or 'edited.png')

        if not content:
            return JsonResponse({'ok': False, 'error': 'No image data'}, status=400)

        # Overwrite existing file keeping same storage path
        storage_name = obj.image.name or f'photos/listing_{obj.listing_id}/edited.png'
        try:
            obj.image.save(storage_name, ContentFile(content), save=True)
            # clear easy-thumbnails cache for this image
            try:
                from easy_thumbnails.files import get_thumbnailer
                get_thumbnailer(obj.image).delete_thumbnails()
            except Exception:
                pass
            return JsonResponse({'ok': True, 'redirect': reverse('admin:listings_listingimage_change', args=[obj.pk])})
        except Exception as e:
            return JsonResponse({'ok': False, 'error': str(e)}, status=500)

    def make_visible(self, request, queryset):
        updated = queryset.update(is_visible=True)
        self.message_user(request, _("Marked %d images as visible") % updated)
    make_visible.short_description = _('Mark selected images as visible')

    def make_hidden(self, request, queryset):
        updated = queryset.update(is_visible=False)
        self.message_user(request, _("Marked %d images as hidden") % updated)
    make_hidden.short_description = _('Mark selected images as hidden')

    def bulk_edit_images(self, request, queryset):
        selected = request.POST.getlist(ACTION_CHECKBOX_NAME)
        select_across = request.POST.get('select_across')

        if 'apply' not in request.POST:
            form = BulkImageEditForm()
            context = {
                'images': queryset,
                'form': form,
                'ids': selected,
                'select_across': select_across,
                'action': 'bulk_edit_images',
            }
            return render(request, 'admin/bulk_edit_images.html', context)

        # Apply
        ids = request.POST.getlist('ids')
        qs = self.model.objects.filter(pk__in=ids) if ids else queryset
        form = BulkImageEditForm(request.POST, request.FILES)
        if not form.is_valid():
            context = {
                'images': qs,
                'form': form,
                'ids': ids,
                'select_across': select_across,
                'action': 'bulk_edit_images',
            }
            return render(request, 'admin/bulk_edit_images.html', context)

        opts = form.cleaned_data
        ok = fail = 0
        from easy_thumbnails.files import get_thumbnailer
        for img in qs.select_related('listing'):
            try:
                if not getattr(img, 'image', None):
                    continue
                process_image(img.image.path, opts)
                try:
                    get_thumbnailer(img.image).delete_thumbnails()
                except Exception:
                    pass
                ok += 1
            except Exception:
                fail += 1
        self.message_user(request, _("Processed %d images, %d failed.") % (ok, fail))
        return redirect(request.get_full_path())
    bulk_edit_images.short_description = _('Bulk edit (watermark/crop/frame)')

    def cover_old_logo(self, request, queryset):
        """Draw a bottom-left triangle to occlude previous company logo."""
        ok = fail = 0
        # Optional overrides via GET/POST if needed later
        size_ratio = 0.24  # ~24% of width
        opacity = 1.0      # solid by default
        color = None       # auto-pick from corner region

        # Process
        for img in queryset.select_related('listing'):
            try:
                if not getattr(img, 'image', None):
                    continue
                add_corner_triangle_to_file(img.image.path, corner='bottom_left', size_ratio=size_ratio, color=color, opacity=opacity)
                try:
                    from easy_thumbnails.files import get_thumbnailer
                    get_thumbnailer(img.image).delete_thumbnails()
                except Exception:
                    pass
                ok += 1
            except Exception:
                fail += 1
        self.message_user(request, _("Applied corner cover on %d images, %d failed.") % (ok, fail))
    cover_old_logo.short_description = _('Cover old logo (triangle BL)')

    def apply_logo_watermark_oneclick(self, request, queryset):
        """One-click: apply default logo with preset position/size to selected images."""

        # Defaults: tuned to typical listing images; adjust if needed
        pos = 'bottom_left'
        opacity = 0.99
        scale = 0.55
        margin = 6

        # Resolve logo path
        logo_path = self._resolve_logo_path()
        import os
        if not os.path.exists(logo_path):
            self.message_user(request, _("Logo not found at %s") % logo_path, level=messages.ERROR)
            return None

        ok, fail = self._apply_logo_batch(queryset, logo_path, pos, opacity, scale, margin)
        self.message_user(request, _("Applied logo (one-click) to %d images, %d failed.") % (ok, fail))
        return None
    apply_logo_watermark_oneclick.short_description = _('Apply logo watermark (one-click)')

    def apply_logo_watermark(self, request, queryset):
        selected = request.POST.getlist(ACTION_CHECKBOX_NAME)
        select_across = request.POST.get('select_across')

        # Default logo path inside repo: coralcity/static/listings.png
        logo_path = self._resolve_logo_path()
        import os
        if not os.path.exists(logo_path):
            self.message_user(request, _("Logo not found at %s") % logo_path, level=messages.ERROR)
            return redirect(request.get_full_path())

        if 'apply' not in request.POST:
            form = LogoWatermarkForm()
            context = {
                'images': queryset,
                'form': form,
                'ids': selected,
                'select_across': select_across,
                'action': 'apply_logo_watermark',
                'logo_path': logo_path,
            }
            return render(request, 'admin/apply_logo_watermark.html', context)

        # Apply
        ids = request.POST.getlist('ids')
        qs = self.model.objects.filter(pk__in=ids) if ids else queryset
        form = LogoWatermarkForm(request.POST)
        if not form.is_valid():
            context = {
                'images': qs,
                'form': form,
                'ids': ids,
                'select_across': select_across,
                'action': 'apply_logo_watermark',
                'logo_path': logo_path,
            }
            return render(request, 'admin/apply_logo_watermark.html', context)

        opts = form.cleaned_data
        pos = opts.get('wm_position') or 'bottom_left'
        opacity = float(opts.get('wm_opacity') or 0.85)
        scale = float(opts.get('wm_scale') or 0.22)
        margin = int(opts.get('wm_margin') or 12)

        ok, fail = self._apply_logo_batch(qs, logo_path, pos, opacity, scale, margin)
        self.message_user(request, _("Applied logo to %d images, %d failed.") % (ok, fail))
        return redirect(request.get_full_path())
    apply_logo_watermark.short_description = _('Apply logo watermark')





class ListingImportJobForm(forms.ModelForm):
    class Meta:
        model = ListingImportJob
        fields = '__all__'

    def clean(self):
        cleaned = super().clean()
        single_url = (cleaned.get('single_url') or '').strip()
        csv_file = cleaned.get('csv_file')
        if not single_url and not csv_file:
            raise forms.ValidationError(_('Provide either a single URL or upload a CSV file.'))
        return cleaned


@admin.register(ListingImportJob)
class ListingImportJobAdmin(admin.ModelAdmin):
    form = ListingImportJobForm
    list_display = (
        'id', 'realtor', 'created_by', 'status', 'created_at', 'started_at', 'finished_at'
    )
    list_filter = ('status', 'realtor')
    search_fields = ('id', 'realtor__name', 'created_by__username', 'single_url')
    readonly_fields = (
        'status', 'log', 'created_at', 'started_at', 'finished_at', 'created_by', 'effective_csv_path'
    )
    fieldsets = (
        (_("Source"), {
            'fields': ('realtor', 'single_url', 'csv_file', 'cookie_file')
        }),
        (_("Options"), {
            'fields': ('delay', 'debug', 'skip_geocode', 'headed', 'images_max', 'no_images')
        }),
        (_("Execution"), {
            'fields': ('status', 'effective_csv_path', 'created_by', 'created_at', 'started_at', 'finished_at', 'log')
        }),
    )

    def effective_csv_path(self, obj):
        return getattr(obj, 'csv_path_cached', '') or ''
    effective_csv_path.short_description = _('CSV path used')

    def save_model(self, request, obj, form, change):
        is_new = obj.pk is None
        if is_new and not getattr(obj, 'created_by_id', None):
            obj.created_by = request.user
        # Reset execution fields on every save if pending
        if is_new:
            obj.status = 'pending'
            obj.log = ''
            obj.started_at = None
            obj.finished_at = None
        super().save_model(request, obj, form, change)

        # Kick off async run when created
        if is_new:
            try:
                start_import_job_async(obj.id)
                self.message_user(request, _("Import job started."), level=messages.INFO)
            except Exception as e:
                self.message_user(request, _("Failed to start job: %s") % e, level=messages.ERROR)
