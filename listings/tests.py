from types import SimpleNamespace

from django.test import SimpleTestCase

from listings.templatetags.portfolio_extras import (
    build_portfolio_meta,
    portfolio_copy_for_language,
    whatsapp_number,
)


class PortfolioPresentationTests(SimpleTestCase):
    def listing(self, **overrides):
        values = {
            "rooms_text": "1+0",
            "bedrooms": "",
            "floor_number": 5,
            "floors_total": 20,
            "source_search_context": {},
        }
        values.update(overrides)
        return SimpleNamespace(**values)

    def comps(self, count=5):
        return [
            {
                "is_same_spec": True,
                "is_available": True,
                "reviews": 12,
            }
            for _ in range(count)
        ]

    def test_french_copy_is_available_without_compiled_locale_files(self):
        copy = portfolio_copy_for_language("fr")
        self.assertEqual(copy["purchase"], "Prix d’achat")
        self.assertEqual(copy["unverified"], "Non vérifiée")

    def test_unverified_is_the_safe_default(self):
        meta = build_portfolio_meta(
            self.listing(),
            self.comps(),
            {"airbnb_roi": 43, "operating_cost_rate": 0.30},
            [],
            language="en",
        )
        self.assertEqual(meta["permit_status"], "unverified")
        self.assertTrue(meta["is_short_stay_conditional"])
        self.assertEqual(meta["confidence_key"], "high")

    def test_verified_status_can_be_supplied_from_listing_source_context(self):
        listing = self.listing(
            source_search_context={
                "portfolio": {
                    "short_term_rental_status": "verified",
                    "short_term_rental_note": "Documents reviewed by the agency.",
                }
            }
        )
        meta = build_portfolio_meta(
            listing,
            self.comps(3),
            {"airbnb_roi": 18, "operating_cost_rate": 0.30},
            [],
            language="en",
        )
        self.assertEqual(meta["permit_status"], "verified")
        self.assertFalse(meta["is_short_stay_conditional"])
        self.assertEqual(meta["permit_note"], "Documents reviewed by the agency.")

    def test_turkish_mobile_phone_is_normalized_for_whatsapp(self):
        self.assertEqual(whatsapp_number("0532 111 22 33"), "905321112233")
