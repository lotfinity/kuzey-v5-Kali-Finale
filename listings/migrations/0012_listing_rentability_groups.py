from django.db import migrations, models
from django.utils.translation import gettext_lazy as _


class Migration(migrations.Migration):

    dependencies = [
        ('listings', '0011_alter_listing_bedrooms'),
    ]

    operations = [
        migrations.AddField(
            model_name='listing',
            name='rentability_groups',
            field=models.CharField(
                blank=True,
                db_index=True,
                default='',
                help_text=_('Tenant/renter groups this apartment is a strong match for.'),
                max_length=255,
                verbose_name=_('Rentability groups'),
            ),
        ),
    ]
