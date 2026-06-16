import os, django, re

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'coralcity.settings')
django.setup()

from listings.models import Listing

TRANSLATION_MAP = {
    'Satılık': 'À vendre',
    'Kiralık': 'À louer',
    'Daire': 'Appartement',
    'Oda': 'Chambre',
    'Metrekare': 'm²',
    'Balkon': 'Balcon',
    'Bahçe': 'Jardin',
    'Geniş': 'Spacieux',
    'Küçük': 'Petit',
    'Yeni': 'Neuf',
    'Eski': 'Ancien',
    'Lüks': 'Luxueux',
    'Eşyalı': 'Meublé',
    'Eşyasız': 'Non meublé',
    'Manzara': 'Vue',
    'Deniz': 'Mer',
    'Deniz manzaralı': 'Vue mer',
    'Şehir': 'Ville',
    'Sıcak': 'Chaud',
    'Soğuk': 'Froid',
}

def translate(t):
    if not t:
        return t
    parts = t.split()
    parts = [TRANSLATION_MAP.get(p, p) for p in parts]
    new = ' '.join(parts)
    new = re.sub(r'\s+', ' ', new).strip()
    if new:
        new = new[0].upper() + new[1:]
    return new[:70]

updated = 0
for l in Listing.objects.all():
    new_title = translate(l.title)
    if new_title != l.title:
        l.title = new_title
        l.save(update_fields=['title'])
        updated += 1
print('Updated', updated, 'titles')
