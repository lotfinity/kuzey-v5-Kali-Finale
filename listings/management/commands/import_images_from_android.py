import json
import os
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.core.files.base import ContentFile

from listings.models import Listing, ListingImage


IMAGES_ROOT = Path("/tmp/sahibinden_images_android")


class Command(BaseCommand):
    help = (
        "Import listing images captured from Android (Sahibinden screenshots). "
        "Reads PNG files from /tmp/sahibinden_images_android/<listing_no>/ "
        "and attaches them as ListingImage records to the matching Listing (by external_id)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--listing-no",
            type=str,
            default="",
            help="Process only this specific listing_no (directory name).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Scan and report what would be done without writing anything.",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Re-import images even if the listing already has images attached.",
        )
        parser.add_argument(
            "--skip-existing",
            action="store_true",
            help="Skip listings that already have any images.",
        )
        parser.add_argument(
            "--rename-to-jpg",
            action="store_true",
            help="Rename .png files to .jpg when storing.",
        )

    def handle(self, *args, **options):
        dry_run = bool(options.get("dry_run"))
        force = bool(options.get("force"))
        skip_existing = bool(options.get("skip_existing"))
        rename_jpg = bool(options.get("rename_to_jpg"))
        single_listing = options.get("listing_no") or ""

        if not IMAGES_ROOT.is_dir():
            raise CommandError(f"Images root not found: {IMAGES_ROOT}")

        # Gather listing directories
        if single_listing:
            dirs = [IMAGES_ROOT / single_listing]
            if not dirs[0].is_dir():
                raise CommandError(f"Directory not found: {dirs[0]}")
        else:
            dirs = sorted(
                [d for d in IMAGES_ROOT.iterdir() if d.is_dir() and d.name.lstrip("-").isdigit()],
                key=lambda d: d.name,
            )

        if not dirs:
            self.stdout.write(self.style.WARNING("No listing directories found."))
            return

        total_imported = 0
        total_skipped = 0
        total_errors = 0

        for listing_dir in dirs:
            external_id = listing_dir.name
            self.stdout.write(f"\n--- Listing {external_id} ---")

            # Find the Listing by external_id
            try:
                listing = Listing.objects.filter(external_id=external_id).first()
            except Exception as e:
                self.stderr.write(self.style.ERROR(f"  DB error: {e}"))
                total_errors += 1
                continue

            if listing is None:
                self.stdout.write(self.style.WARNING(f"  No Listing found with external_id={external_id}, skipping"))
                total_skipped += 1
                continue

            listing_ref = f"Listing #{listing.pk} - {listing.title[:60]}"

            # Check existing images
            existing_images = list(listing.images.all())
            if existing_images:
                if skip_existing:
                    self.stdout.write(f"  {listing_ref} already has {len(existing_images)} image(s), skipping (--skip-existing)")
                    total_skipped += 1
                    continue
                if not force:
                    self.stdout.write(
                        self.style.WARNING(
                            f"  {listing_ref} already has {len(existing_images)} image(s). "
                            "Use --force to re-import (removes existing images first)."
                        )
                    )
                    total_skipped += 1
                    continue

            # Read manifest if present
            manifest_path = listing_dir / "manifest.json"
            image_files: list[str] = []
            duplicate_indices: set[int] = set()

            if manifest_path.is_file():
                try:
                    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                    manifest_images = manifest.get("images") or []
                    for entry in manifest_images:
                        idx = entry.get("index", 0)
                        fname = entry.get("file", "")
                        if not fname:
                            continue
                        if entry.get("duplicate_of"):
                            duplicate_indices.add(idx)
                            continue
                        full_path = listing_dir / fname
                        if full_path.is_file():
                            image_files.append(fname)
                except Exception as e:
                    self.stdout.write(self.style.WARNING(f"  Could not parse manifest.json: {e}"))
                    image_files = []

            if not image_files:
                # Fallback: scan directory for .png files
                image_files = sorted(
                    [f.name for f in sorted(listing_dir.iterdir()) if f.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp")],
                    key=lambda n: int("".join(c for c in n if c.isdigit()) or 0),
                )

            if not image_files:
                self.stdout.write(self.style.WARNING(f"  No image files found in {listing_dir}"))
                total_skipped += 1
                continue

            self.stdout.write(f"  {listing_ref} — {len(image_files)} image(s) to import")

            if dry_run:
                self.stdout.write(f"  [DRY-RUN] Would import {len(image_files)} images")
                total_imported += len(image_files)
                continue

            # Remove existing images if --force
            if force and existing_images:
                for img in existing_images:
                    try:
                        img.image.delete(save=False)
                        img.delete()
                    except Exception as e:
                        self.stdout.write(self.style.WARNING(f"  Could not delete existing image {img.pk}: {e}"))
                self.stdout.write(f"  Removed {len(existing_images)} existing image(s)")

            # Import images
            imported_count = 0
            errors = 0
            for i, fname in enumerate(image_files):
                src_path = listing_dir / fname
                try:
                    data = src_path.read_bytes()
                    if not data:
                        self.stdout.write(self.style.WARNING(f"  Empty file: {fname}, skipping"))
                        continue

                    # Determine target filename
                    if rename_jpg:
                        target_name = f"{i + 1:03d}.jpg"
                    else:
                        target_name = fname

                    img = ListingImage(
                        listing=listing,
                        order=i,
                        is_primary=(i == 0),
                        is_visible=True,
                    )
                    img.image.save(target_name, ContentFile(data), save=True)
                    imported_count += 1
                except Exception as e:
                    self.stderr.write(self.style.ERROR(f"  Failed to import {fname}: {e}"))
                    errors += 1

            total_imported += imported_count
            total_errors += errors
            self.stdout.write(self.style.SUCCESS(f"  Imported {imported_count} image(s) for listing #{listing.pk}"))

        summary = f"Done. Imported={total_imported}, Skipped={total_skipped}, Errors={total_errors}"
        if dry_run:
            summary += " (dry-run)"
        self.stdout.write(self.style.SUCCESS(summary))
