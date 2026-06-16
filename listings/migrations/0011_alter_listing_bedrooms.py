from django.db import migrations, models


def convert_bedrooms(apps, schema_editor):
    Listing = apps.get_model('listings', 'Listing')
    for listing in Listing.objects.all():
        raw = str(listing.bedrooms).strip()
        if raw == '1':
            listing.bedrooms = '1+0'
        elif raw in ('0', '', 'None'):
            listing.bedrooms = ''
        listing.save(update_fields=['bedrooms'])


class Migration(migrations.Migration):

    dependencies = [
        ('listings', '0010_alter_listingimportjob_options_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='listing',
            name='bedrooms',
            field=models.CharField(blank=True, default='', max_length=20),
        ),
        migrations.RunPython(convert_bedrooms, migrations.RunPython.noop),
    ]
