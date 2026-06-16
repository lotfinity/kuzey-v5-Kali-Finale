"""Interactive command to translate listing titles from Turkish to French.

The previous ``translate_titles_french`` command performed a bulk replace based
on a static word‑map.  This version lets you handle each listing manually – the
operator sees the current title, can type a new French title (or press Enter to
keep the existing one), and the change is saved immediately.

Usage::

    ./venv/bin/python manage.py translate_titles_interactive

The command walks through all ``Listing`` objects ordered by primary key.  For
each listing it prints the ID and the current title, then prompts for a new
title.  If the user provides an empty input the original title is left
unchanged.  After each entry the command shows a short confirmation.

This approach gives full control without relying on an automatic word map.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from listings.models import Listing


class Command(BaseCommand):
    help = "Interactively translate listing titles from Turkish to French."

    def add_arguments(self, parser):
        parser.add_argument(
            "--skip-existing",
            action="store_true",
            help="If set, listings that already have a French‑style title (detected by a leading 'À') are skipped.",
        )

    def handle(self, *args, **options):
        skip_existing = options.get("skip_existing")
        total = Listing.objects.count()
        self.stdout.write(f"Processing {total} listings (interactive mode)…")

        updated = 0
        for listing in Listing.objects.order_by("pk"):
            original = listing.title or ""
            # Simple heuristic: if the title already starts with a French word we assume it was translated.
            if skip_existing and original.startswith("À"):
                continue

            self.stdout.write(f"\nListing #{listing.pk}: {original}")
            try:
                # ``input`` works in the terminal; it blocks until the user types.
                new_title = input("Enter new French title (or press Enter to keep): ").strip()
            except EOFError:
                # In case the command is piped or input is closed.
                raise CommandError("Input stream closed unexpectedly.")

            if not new_title:
                # No change requested.
                self.stdout.write("  → kept unchanged")
                continue

            listing.title = new_title
            listing.save(update_fields=["title"])
            updated += 1
            self.stdout.write(self.style.SUCCESS(f"  → updated to: {new_title}"))

        self.stdout.write(self.style.SUCCESS(f"Finished. Updated {updated} listings."))
