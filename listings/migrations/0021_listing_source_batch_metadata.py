from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("listings", "0020_listing_airbnb_rent_estimates"),
    ]

    operations = [
        migrations.AddField(
            model_name="listing",
            name="source_batch_label",
            field=models.CharField(blank=True, db_index=True, max_length=120),
        ),
        migrations.AddField(
            model_name="listing",
            name="source_search_context",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
