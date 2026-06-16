import json
import subprocess
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from listings.models import Listing


class Command(BaseCommand):
    help = "Scroll Android index pages, extract listings missing from DB, and import each viewport."

    def add_arguments(self, parser):
        parser.add_argument(
            "--script",
            default="/home/lofa/sahibinden-android-pipeline/scripts/run_visible_index.py",
            help="Full Android listing extraction script path",
        )
        parser.add_argument(
            "--targets-json",
            default="/tmp/sahibinden_listing_targets.json",
            help="Temporary target file passed to the Android script",
        )
        parser.add_argument(
            "--results-json",
            default="/tmp/sahibinden_full_index/results.json",
            help="Android script output to import",
        )
        parser.add_argument(
            "--realtor-id",
            type=int,
            default=1,
            help="Realtor ID assigned to newly imported listings",
        )
        parser.add_argument(
            "--max-pages",
            type=int,
            default=10,
            help="Maximum visible result pages to process",
        )
        parser.add_argument(
            "--dry-run-import",
            action="store_true",
            help="Run extraction but dry-run database imports",
        )
        parser.add_argument(
            "--no-import",
            action="store_true",
            help="Run extraction but do not import results",
        )
        parser.add_argument(
            "--batch-label",
            default="",
            help="Optional label applied to imported Listing.source_batch_label",
        )

    def handle(self, *args, **options):
        script = Path(options["script"])
        targets_json = Path(options["targets_json"])
        results_json = Path(options["results_json"])

        if not script.exists():
            raise CommandError(f"Android script not found: {script}")

        def export_targets():
            call_command("export_android_listing_targets", str(targets_json))

        def import_results():
            if options["no_import"]:
                self.stdout.write(self.style.WARNING("Skipping database import because --no-import was passed."))
                return
            if not results_json.exists():
                raise CommandError(f"Results JSON not found after Android run: {results_json}")

            listing_import_args = [
                str(results_json),
                "--realtor-id",
                str(options["realtor_id"]),
                "--source-status-ok-only",
            ]
            if options["dry_run_import"]:
                listing_import_args.append("--dry-run")
            if options["batch_label"]:
                listing_import_args.extend(["--source-batch-label", options["batch_label"]])
            call_command("import_hot_listings", *listing_import_args)

            phone_import_args = [str(results_json)]
            if options["dry_run_import"]:
                phone_import_args.append("--dry-run")
            call_command("import_android_results", *phone_import_args)
            if not options["dry_run_import"]:
                call_command("resolve_listing_phone_entries")

        def result_fingerprint():
            if not results_json.exists():
                return ()
            try:
                rows = json.loads(results_json.read_text(encoding="utf-8"))
            except Exception:
                return ()
            return tuple(
                (str(row.get("listing_no") or ""), str(row.get("source_index_title") or ""), str(row.get("source_index_price") or ""))
                for row in rows
                if isinstance(row, dict)
            )

        def scroll_next_page():
            subprocess.run(["adb", "shell", "input", "swipe", "540", "1900", "540", "650", "650"], check=False)

        self.stdout.write(
            self.style.NOTICE(
                "DB listings before run: total=%s"
                % Listing.objects.count()
            )
        )

        previous_fingerprint = None
        repeated_pages = 0
        for page in range(1, options["max_pages"] + 1):
            export_targets()
            targets = json.loads(targets_json.read_text(encoding="utf-8"))
            missing_from_db = targets.get("summary", {}).get("missing_from_db")
            self.stdout.write(
                self.style.NOTICE(
                    "Viewport %s/%s starting. Observed missing from DB=%s"
                    % (page, options["max_pages"], missing_from_db)
                )
            )
            if not targets.get("target_listing_nos"):
                self.stdout.write(self.style.SUCCESS("No observed index targets are missing from DB."))
                break

            completed = subprocess.run(
                ["python3", str(script), "--targets-json", str(targets_json)],
                text=True,
            )
            if completed.returncode != 0:
                raise CommandError(f"Android extraction failed with exit code {completed.returncode}")

            fingerprint = result_fingerprint()
            if fingerprint == previous_fingerprint:
                repeated_pages += 1
            else:
                repeated_pages = 0
            previous_fingerprint = fingerprint

            import_results()
            self.stdout.write(
                self.style.SUCCESS(
                    "Viewport %s imported. DB listings now=%s"
                    % (page, Listing.objects.count())
                )
            )

            if repeated_pages >= 2:
                self.stdout.write(self.style.WARNING("Stopping: repeated visible page after scrolling."))
                break
            if page < options["max_pages"]:
                scroll_next_page()
