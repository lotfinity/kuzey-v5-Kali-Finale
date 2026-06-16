"""Management command to improve listing titles by converting Turkish keywords
to short, attractive French equivalents.

The command does **not** perform a full translation – it simply replaces a set
of common Turkish words that appear in titles with concise French alternatives.
This keeps the titles short, readable and more appealing to a French‑speaking
audience.

Usage::

    ./venv/bin/python manage.py translate_titles_french [--dry-run]

Options
-------
``--dry-run``
    Show the proposed changes without saving them to the database.

The command iterates over all ``Listing`` objects, applies a word‑by‑word
replacement defined in ``TRANSLATION_MAP`` and saves the new title.
"""

from __future__ import annotations

import re
from typing import Dict

from django.core.management.base import BaseCommand, CommandError

from listings.models import Listing

# Simple word‑level mapping from Turkish to French.  Only the most common
# adjectives/nouns that appear in our dataset are included.  Unmapped words are
# left untouched.
TRANSLATION_MAP: Dict[str, str] = {
    "Satılık": "À vendre",
    "Kiralık": "À louer",
    "Daire": "Appartement",
    "Oda": "Chambre",
    "Metrekare": "m²",
    "Metre": "mètre",
    "Balkon": "Balcon",
    "Bahçe": "Jardin",
    "Geniş": "Spacieux",
    "Küçük": "Petit",
    "Yeni": "Neuf",
    "Eski": "Ancien",
    "Lüks": "Luxueux",
    "Eşyalı": "Meublé",
    "Eşyasız": "Non meublé",
    "Manzara": "Vue",
    "Deniz": "Mer",
    "Deniz manzaralı": "Vue mer",
    "Şehir": "Ville",
    "Sıcak": "Chaud",
    "Soğuk": "Froid",
}


def translate_title(original: str) -> str:
    """Return a French‑styled title.

    The function splits the original title on whitespace, replaces any word that
    exists in ``TRANSLATION_MAP`` and then joins the parts back together.  It also
    collapses multiple spaces and trims the result to a maximum of 70
    characters for brevity.
    """
    # Preserve original spacing for words not in the map.
    parts = original.split()
    translated_parts = [TRANSLATION_MAP.get(p, p) for p in parts]
    translated = " ".join(translated_parts)
    # Collapse any accidental double spaces and trim length.
    translated = re.sub(r"\s+", " ", translated).strip()
    return translated[:70]


class Command(BaseCommand):
    help = "Replace Turkish keywords in listing titles with short French equivalents."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show changes without saving them to the database.",
        )

    def handle(self, *args, **options):
        dry_run = options.get("dry_run")
        total = Listing.objects.count()
        self.stdout.write(f"Processing {total} listings…")

        updated = 0
        for listing in Listing.objects.all():
            original = listing.title or ""
            new_title = translate_title(original)
            if new_title != original:
                if dry_run:
                    self.stdout.write(
                        f"[DRY] Listing #{listing.pk}: '{original}' → '{new_title}'"
                    )
                else:
                    listing.title = new_title
                    listing.save(update_fields=["title"])
                    self.stdout.write(
                        f"Updated Listing #{listing.pk}: '{original}' → '{new_title}'"
                    )
                updated += 1

        self.stdout.write(self.style.SUCCESS(f"Finished. Updated {updated} listings."))
