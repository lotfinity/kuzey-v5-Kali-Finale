import json
import subprocess
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from listings.models import Listing


class Command(BaseCommand):
    help = "Export missing phone targets, run Android extraction, then import phones into listings."

    def add_arguments(self, parser):
        parser.add_argument(
            "--script",
            default="/home/lofa/sahibinden-android-pipeline/scripts/run_visible_index_phones.py",
            help="Android extraction script path",
        )
        parser.add_argument(
            "--targets-json",
            default="/tmp/sahibinden_phone_targets.json",
            help="Temporary target file passed to the Android script",
        )
        parser.add_argument(
            "--results-json",
            default="/tmp/sahibinden_phone_index/results.json",
            help="Android script output to import",
        )
        parser.add_argument(
            "--scraped-results",
            action="append",
            default=[],
            help="Existing Android results.json files to count as already scraped",
        )
        parser.add_argument(
            "--skip-run",
            action="store_true",
            help="Do not run Android automation; import the existing results JSON only",
        )
        parser.add_argument(
            "--no-import",
            action="store_true",
            help="Run Android automation but do not import results into the database",
        )
        parser.add_argument(
            "--details",
            action="store_true",
            help="Import coordinates and parsed detail fields in addition to phone",
        )
        parser.add_argument(
            "--dry-run-import",
            action="store_true",
            help="Show database imports without writing changes",
        )
        parser.add_argument(
            "--max-pages",
            type=int,
            default=10,
            help="Maximum visible result pages the phone scraper should process",
        )
        parser.add_argument(
            "--legacy-whole-run",
            action="store_true",
            help="Let the phone script handle all pages itself, then import once at the end",
        )

    def handle(self, *args, **options):
        script = Path(options["script"])
        targets_json = Path(options["targets_json"])
        results_json = Path(options["results_json"])

        if not script.exists():
            raise CommandError(f"Android script not found: {script}")

        def export_targets():
            export_args = [str(targets_json)]
            for scraped_path in options["scraped_results"]:
                export_args.extend(["--scraped-results", scraped_path])
            call_command("export_android_phone_targets", *export_args)

        def import_results():
            if options["no_import"]:
                self.stdout.write(self.style.WARNING("Skipping database import because --no-import was passed."))
                return
            if not results_json.exists():
                raise CommandError(f"Results JSON not found after Android run: {results_json}")
            import_args = [str(results_json)]
            if options["details"]:
                import_args.append("--details")
            if options["dry_run_import"]:
                import_args.append("--dry-run")
            call_command("import_android_results", *import_args)
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

        total = Listing.objects.count()
        with_phone = Listing.objects.exclude(phone="").count()
        missing = Listing.objects.filter(phone="").count()
        self.stdout.write(
            self.style.NOTICE(
                "DB listing phone coverage before run: total=%s with_phone=%s missing=%s"
                % (total, with_phone, missing)
            )
        )

        export_targets()

        if not options["skip_run"]:
            if not options["legacy_whole_run"]:
                previous_fingerprint = None
                repeated_pages = 0
                for page in range(1, options["max_pages"] + 1):
                    remaining = Listing.objects.filter(phone="").count()
                    self.stdout.write(
                        self.style.NOTICE(
                            "Viewport %s/%s starting. DB missing phones=%s"
                            % (page, options["max_pages"], remaining)
                        )
                    )
                    if remaining == 0:
                        self.stdout.write(self.style.SUCCESS("All listing phones are filled."))
                        break

                    export_targets()
                    completed = subprocess.run(
                        [
                            "python3",
                            str(script),
                            "--targets-json",
                            str(targets_json),
                            "--max-pages",
                            "1",
                        ],
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

                    after_missing = Listing.objects.filter(phone="").count()
                    self.stdout.write(
                        self.style.SUCCESS(
                            "Viewport %s imported. DB missing phones now=%s"
                            % (page, after_missing)
                        )
                    )
                    if after_missing == 0:
                        self.stdout.write(self.style.SUCCESS("All listing phones are filled."))
                        break
                    if repeated_pages >= 2:
                        self.stdout.write(self.style.WARNING("Stopping: repeated visible page after scrolling."))
                        break
                    if page < options["max_pages"]:
                        scroll_next_page()
                return

            self.stdout.write(self.style.NOTICE(f"Running Android extraction with targets: {targets_json}"))
            completed = subprocess.run(
                [
                    "python3",
                    str(script),
                    "--targets-json",
                    str(targets_json),
                    "--max-pages",
                    str(options["max_pages"]),
                ],
                text=True,
            )
            if completed.returncode != 0:
                raise CommandError(f"Android extraction failed with exit code {completed.returncode}")

        import_results()
