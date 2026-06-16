from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('listings', '0013_currencysettings'),
    ]

    operations = [
        migrations.CreateModel(
            name='WhatsAppConversation',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('chat_id', models.CharField(db_index=True, max_length=120)),
                ('phone_number', models.CharField(db_index=True, max_length=32)),
                ('display_name', models.CharField(blank=True, max_length=160)),
                ('session', models.CharField(blank=True, db_index=True, max_length=80)),
                ('last_synced_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('listing', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='whatsapp_conversations', to='listings.Listing')),
            ],
            options={
                'ordering': ('-updated_at',),
                'unique_together': {('listing', 'chat_id', 'session')},
            },
        ),
        migrations.CreateModel(
            name='WhatsAppMessage',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('waha_message_id', models.CharField(blank=True, db_index=True, max_length=255)),
                ('direction', models.CharField(choices=[('in', 'Incoming'), ('out', 'Outgoing')], db_index=True, max_length=8)),
                ('sender', models.CharField(blank=True, max_length=120)),
                ('body', models.TextField(blank=True)),
                ('message_type', models.CharField(blank=True, max_length=40)),
                ('sent_at', models.DateTimeField(blank=True, db_index=True, null=True)),
                ('raw_payload', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('conversation', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='messages', to='listings.WhatsAppConversation')),
            ],
            options={
                'ordering': ('sent_at', 'id'),
            },
        ),
    ]
