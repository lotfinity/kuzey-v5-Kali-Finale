import json
import subprocess
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from listings.models import Listing


class Command(BaseCommand):
    help = "Capture Android gallery screenshots for listings without images and import each viewport."

    def add_arguments(self, parser):
        parser.add_argument(
            "--script",
            default="/home/lofa/sahibinden-android-pipeline/scripts/capture_listing_images_android.py",
            help="Android image capture script path",
        )
        parser.add_argument(
            "--targets-json",
            default="/tmp/sahibinden_image_targets.json",
            help="Temporary image target JSON",
        )
        parser.add_argument(
            "--output",
            default="/tmp/sahibinden_images_android",
            help="Android image capture output folder",
        )
        parser.add_argument(
            "--max-pages",
            type=int,
            default=10,
            help="Maximum visible result pages to process",
        )
        parser.add_argument(
            "--image-wait",
            type=float,
            default=0.45,
            help="Seconds to wait after each gallery swipe",
        )
        parser.add_argument(
            "--dry-run-import",
            action="store_true",
            help="Capture images but dry-run the Django import",
        )
        parser.add_argument(
            "--no-import",
            action="store_true",
            help="Capture images but do not import them",
        )

    def handle(self, *args, **options):
        script = Path(options["script"])
        targets_json = Path(options["targets_json"])
        output = Path(options["output"])

        if not script.exists():
            raise CommandError(f"Android image script not found: {script}")

        def export_targets():
            call_command("export_android_image_targets", str(targets_json))

        def import_images():
            if options["no_import"]:
                self.stdout.write(self.style.WARNING("Skipping image import because --no-import was passed."))
                return
            import_args = ["--skip-existing"]
            if options["dry_run_import"]:
                import_args.append("--dry-run")
            call_command("import_images_from_android", *import_args)

        def result_fingerprint():
            manifest = output / "images_manifest.json"
            if not manifest.exists():
                return ()
            try:
                rows = json.loads(manifest.read_text(encoding="utf-8"))
            except Exception:
                return ()
            return tuple(str(row.get("listing_no") or "") for row in rows if isinstance(row, dict))

        def scroll_next_page():
            subprocess.run(["adb", "shell", "input", "swipe", "540", "1900", "540", "650", "650"], check=False)

        total = Listing.objects.count()
        with_images = Listing.objects.filter(images__isnull=False).distinct().count()
        without_images = Listing.objects.filter(images__isnull=True).count()
        self.stdout.write(
            self.style.NOTICE(
                "DB image coverage before run: total=%s with_images=%s without_images=%s"
                % (total, with_images, without_images)
            )
        )

        previous_fingerprint = None
        repeated_pages = 0
        for page in range(1, options["max_pages"] + 1):
            export_targets()
            targets = json.loads(targets_json.read_text(encoding="utf-8"))
            self.stdout.write(
                self.style.NOTICE(
                    "Viewport %s/%s starting. Image targets=%s"
                    % (page, options["max_pages"], len(targets))
                )
            )
            if not targets:
                self.stdout.write(self.style.SUCCESS("All listings have images."))
                break

            completed = subprocess.run(
                [
                    "python3",
                    str(script),
                    "--input",
                    str(targets_json),
                    "--output",
                    str(output),
                    "--visible-index",
                    "--targets-only",
                    "--image-wait",
                    str(options["image_wait"]),
                ],
                text=True,
            )
            if completed.returncode != 0:
                raise CommandError(f"Android image capture failed with exit code {completed.returncode}")

            fingerprint = result_fingerprint()
            if fingerprint == previous_fingerprint:
                repeated_pages += 1
            else:
                repeated_pages = 0
            previous_fingerprint = fingerprint

            import_images()

            with_images = Listing.objects.filter(images__isnull=False).distinct().count()
            without_images = Listing.objects.filter(images__isnull=True).count()
            self.stdout.write(
                self.style.SUCCESS(
                    "Viewport %s imported. with_images=%s without_images=%s"
                    % (page, with_images, without_images)
                )
            )

            if without_images == 0:
                self.stdout.write(self.style.SUCCESS("All listings have images."))
                break
            if repeated_pages >= 2:
                self.stdout.write(self.style.WARNING("Stopping: repeated image manifest after scrolling."))
                break
            if page < options["max_pages"]:
                scroll_next_page()
