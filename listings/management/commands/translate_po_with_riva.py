import json
import os
import time

import polib
import requests
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Translate missing .po entries with the NVIDIA Riva translation instruct model."

    def add_arguments(self, parser):
        parser.add_argument("--po-file", default="locale/fr/LC_MESSAGES/django.po")
        parser.add_argument("--language", default="French")
        parser.add_argument("--api-key", default=os.environ.get("NVIDIA_API_KEY", ""))
        parser.add_argument("--endpoint", default="https://integrate.api.nvidia.com/v1/chat/completions")
        parser.add_argument("--model", default="nvidia/riva-translate-4b-instruct-v1.1")
        parser.add_argument("--only-reference", default="", help="Translate only entries whose source reference contains this text.")
        parser.add_argument("--limit", type=int, default=0, help="Maximum entries to translate. 0 means no limit.")
        parser.add_argument("--batch-size", type=int, default=20)
        parser.add_argument("--overwrite", action="store_true")
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--compile", action="store_true", dest="compile_messages")
        parser.add_argument("--sleep", type=float, default=0.2)

    def handle(self, *args, **options):
        if not options["api_key"]:
            raise CommandError("Set NVIDIA_API_KEY or pass --api-key.")

        po = polib.pofile(options["po_file"])
        entries = []
        only_reference = options["only_reference"].strip()
        for entry in po:
            if entry.obsolete or entry.msgid_plural:
                continue
            if only_reference and only_reference not in " ".join(ref for ref, _ in entry.occurrences):
                continue
            if entry.msgstr and not options["overwrite"]:
                continue
            if not entry.msgid.strip():
                continue
            entries.append(entry)

        if options["limit"]:
            entries = entries[: options["limit"]]

        if not entries:
            self.stdout.write(self.style.SUCCESS("No entries need translation."))
            return

        translated = 0
        for start in range(0, len(entries), options["batch_size"]):
            batch = entries[start : start + options["batch_size"]]
            if "riva-translate" in options["model"].lower():
                translations = {
                    str(idx): self.translate_text(entry.msgid, options)
                    for idx, entry in enumerate(batch)
                }
            else:
                payload = {str(idx): entry.msgid for idx, entry in enumerate(batch)}
                translations = self.translate_batch(payload, options)
            for idx, entry in enumerate(batch):
                translated_text = str(translations.get(str(idx), "")).strip()
                if not translated_text:
                    self.stdout.write(self.style.WARNING("Missing translation for: %s" % entry.msgid[:80]))
                    continue
                if "%%" in entry.msgid and "%%" not in translated_text:
                    translated_text = translated_text.replace("%", "%%")
                if options["dry_run"]:
                    self.stdout.write("%s => %s" % (entry.msgid, translated_text))
                else:
                    entry.msgstr = translated_text
                translated += 1
            if options["sleep"]:
                time.sleep(options["sleep"])

        if not options["dry_run"]:
            po.save()
            if options["compile_messages"]:
                call_command("compilemessages", locale=["fr"])

        self.stdout.write(self.style.SUCCESS("Translated %s entries in %s." % (translated, options["po_file"])))

    def translate_text(self, text, options):
        response = requests.post(
            options["endpoint"],
            headers={
                "Authorization": "Bearer %s" % options["api_key"],
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            json={
                "model": options["model"],
                "messages": [
                    {
                        "role": "system",
                        "content": "en-fr",
                    },
                    {
                        "role": "user",
                        "content": text,
                    },
                ],
                "temperature": 0.0,
                "max_tokens": 1024,
            },
            timeout=90,
        )
        if response.status_code >= 400:
            raise CommandError("Translation API error %s: %s" % (response.status_code, response.text[:500]))
        data = response.json()
        try:
            return data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError, TypeError) as exc:
            raise CommandError("Unexpected translation response: %s" % data) from exc

    def translate_batch(self, payload, options):
        prompt = (
            "Translate each JSON value into %s for a Django web application. "
            "Keep placeholders, punctuation, currencies, HTML tags, and command text intact. "
            "Return only a valid JSON object with the same keys and translated string values.\n\n%s"
            % (options["language"], json.dumps(payload, ensure_ascii=False))
        )
        response = requests.post(
            options["endpoint"],
            headers={
                "Authorization": "Bearer %s" % options["api_key"],
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            json={
                "model": options["model"],
                "messages": [
                    {
                        "role": "system",
                        "content": "You are a precise software localization translator.",
                    },
                    {
                        "role": "user",
                        "content": prompt,
                    },
                ],
                "temperature": 0.0,
                "max_tokens": 2048,
            },
            timeout=90,
        )
        if response.status_code >= 400:
            raise CommandError("Translation API error %s: %s" % (response.status_code, response.text[:500]))
        data = response.json()
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise CommandError("Unexpected translation response: %s" % data) from exc
        content = content.strip()
        if content.startswith("```"):
            content = content.strip("`")
            if content.lower().startswith("json"):
                content = content[4:].strip()
        try:
            result = json.loads(content)
        except json.JSONDecodeError as exc:
            raise CommandError("Translation response was not JSON: %s" % content[:500]) from exc
        if not isinstance(result, dict):
            raise CommandError("Translation response must be a JSON object.")
        return result
