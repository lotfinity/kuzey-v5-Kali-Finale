from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('listings', '0019_airbnblisting'),
    ]

    operations = [
        migrations.AddField(
            model_name='listing',
            name='airbnb_comp_count',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name='listing',
            name='airbnb_comp_median_try',
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='listing',
            name='estimated_monthly_rent_try',
            field=models.IntegerField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name='listing',
            name='rent_estimate_source',
            field=models.CharField(blank=True, max_length=80),
        ),
        migrations.AddField(
            model_name='listing',
            name='rent_estimate_updated_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
