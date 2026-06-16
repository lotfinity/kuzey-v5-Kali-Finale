from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('listings', '0018_alter_listingphoneentry_scraped_at'),
    ]

    operations = [
        migrations.CreateModel(
            name='AirbnbListing',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('listing_id', models.CharField(db_index=True, max_length=40, unique=True)),
                ('title', models.CharField(blank=True, max_length=255)),
                ('tagline', models.CharField(blank=True, max_length=255)),
                ('property_type', models.CharField(blank=True, max_length=120)),
                ('listing_url', models.URLField(blank=True, max_length=500)),
                ('booking_url', models.URLField(blank=True, max_length=700)),
                ('city', models.CharField(blank=True, max_length=160)),
                ('full_address', models.CharField(blank=True, max_length=300)),
                ('location', models.CharField(blank=True, max_length=300)),
                ('latitude', models.FloatField(blank=True, null=True)),
                ('longitude', models.FloatField(blank=True, null=True)),
                ('bedroom_count', models.PositiveSmallIntegerField(blank=True, null=True)),
                ('bathroom_count', models.DecimalField(blank=True, decimal_places=1, max_digits=4, null=True)),
                ('bed_count', models.PositiveSmallIntegerField(blank=True, null=True)),
                ('guest_capacity', models.PositiveSmallIntegerField(blank=True, null=True)),
                ('photos', models.JSONField(blank=True, default=list)),
                ('highlights', models.JSONField(blank=True, default=list)),
                ('amenity_ids', models.JSONField(blank=True, default=list)),
                ('host_id', models.CharField(blank=True, max_length=40)),
                ('host_name', models.CharField(blank=True, max_length=160)),
                ('host_avatar', models.URLField(blank=True, max_length=700)),
                ('is_superhost', models.BooleanField(default=False)),
                ('is_verified', models.BooleanField(blank=True, null=True)),
                ('host_rating', models.DecimalField(blank=True, decimal_places=2, max_digits=4, null=True)),
                ('host_review_count', models.PositiveIntegerField(blank=True, null=True)),
                ('years_hosting', models.PositiveSmallIntegerField(blank=True, null=True)),
                ('overall_rating', models.DecimalField(blank=True, decimal_places=2, max_digits=4, null=True)),
                ('review_count', models.PositiveIntegerField(blank=True, null=True)),
                ('rating_categories', models.JSONField(blank=True, default=list)),
                ('is_guest_favorite', models.BooleanField(blank=True, null=True)),
                ('nightly_rate', models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                ('currency', models.CharField(blank=True, max_length=8)),
                ('total_cost', models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                ('pricing', models.JSONField(blank=True, default=dict)),
                ('cancellation_policy', models.CharField(blank=True, max_length=160)),
                ('cancellation_terms', models.JSONField(blank=True, default=list)),
                ('is_rare_find', models.BooleanField(default=False)),
                ('is_available', models.BooleanField(blank=True, null=True)),
                ('unavailability_reason', models.CharField(blank=True, max_length=255)),
                ('rank', models.PositiveIntegerField(blank=True, db_index=True, null=True)),
                ('source_destination_query', models.CharField(blank=True, db_index=True, max_length=255)),
                ('search_adult_guests', models.PositiveSmallIntegerField(blank=True, null=True)),
                ('search_page_number', models.PositiveIntegerField(blank=True, null=True)),
                ('raw_search_payload', models.JSONField(blank=True, default=dict)),
                ('raw_details_payload', models.JSONField(blank=True, default=dict)),
                ('scraped_at', models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ('details_scraped_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Airbnb listing',
                'verbose_name_plural': 'Airbnb listings',
                'ordering': ('rank', '-overall_rating', 'title'),
            },
        ),
    ]
