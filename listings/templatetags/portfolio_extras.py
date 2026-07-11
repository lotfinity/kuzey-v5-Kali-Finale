from urllib.parse import quote_plus

from django import template
from django.utils.translation import get_language

register = template.Library()


COPY = {
    "en": {
        "investment_portfolio": "Investment Portfolio",
        "special_portfolio": "Special listing portfolio",
        "purchase": "Purchase",
        "quoted_30_night_median": "Median quoted 30-night price",
        "conditional_roi": "Conditional annual return",
        "estimated_before_tax": "Estimated before tax",
        "conditional": "Conditional",
        "short_term_status": "Short-term rental eligibility",
        "unverified": "Unverified",
        "verified": "Verified",
        "restricted": "Restricted",
        "not_permitted": "Not permitted",
        "permit_unverified_note": "Tourism-rental eligibility and the building management plan have not been verified. Treat every short-stay return as a conditional scenario until written confirmation is obtained.",
        "permit_verified_note": "The listing record marks short-term rental eligibility as verified. Review the supporting permit and building documents before relying on the scenario.",
        "permit_restricted_note": "Short-term rental may be subject to building, management-plan, permit, or operational restrictions. Confirm the exact conditions before relying on the scenario.",
        "permit_not_permitted_note": "The listing record indicates short-term rental is not permitted. Use the long-term scenario for underwriting.",
        "map_intelligence": "Map intelligence",
        "airbnb_comps_title": "Airbnb comparisons around the asset",
        "why_location_matters": "Why this location matters",
        "fresh_evidence": "Fresh Airbnb evidence",
        "rental_set": "30-night quoted-price set",
        "rental_set_intro": "Exact-unit matches are separated from broader nearby context. Quoted prices are evidence, not guaranteed recurring occupancy or revenue.",
        "underwriting_market": "Underwriting market",
        "comp_count": "Primary comp count",
        "exact_matches": "Exact / close-spec matches",
        "availability_checked": "Availability checked",
        "reviewed_comps": "Comps with reviews",
        "confidence": "Evidence confidence",
        "high": "High",
        "medium": "Medium",
        "low": "Low",
        "price_band": "P25 / Median / P75",
        "comp_range": "Quoted range",
        "same_spec": "Close specification",
        "context_comp": "Broader context",
        "available": "Available",
        "unavailable": "Unavailable",
        "availability_unchecked": "Availability unchecked",
        "guest_favorite": "Guest favorite",
        "rare_find": "Rare find",
        "new_unrated": "new / unrated",
        "rating": "rating",
        "listing_reviews": "listing reviews",
        "host_reviews": "host reviews",
        "years_hosting": "yrs hosting",
        "verified_host": "Verified",
        "days_30": "30 nights",
        "per_night": "/night",
        "previous_comp": "Previous Airbnb comparison",
        "next_comp": "Next Airbnb comparison",
        "swipe_comps": "Swipe comparisons",
        "strategic_demand": "Strategic demand",
        "calendar_source": "Calendar source: official TÜYAP fair calendar, checked July 4, 2026.",
        "rentability": "Return scenarios",
        "yield_scenarios": "Debt-free return scenarios",
        "scenario_intro": "Calculations use purchase price, furnishing and closing reserves. Airbnb figures apply a pooled operating reserve and remain conditional on legal eligibility, actual occupancy and execution quality.",
        "long_term_fallback": "Long-term fallback",
        "airbnb_base": "Short-stay base",
        "operator_upside": "Operator upside",
        "estimated_monthly_net": "Estimated monthly net",
        "gross_rent": "Gross rent",
        "gross_revenue": "Quoted gross revenue",
        "annual_net_roi": "Estimated annual return",
        "investment_read": "Investment read",
        "operating_assumptions": "Operating reserve assumptions",
        "operating_assumptions_intro": "Illustrative allocation of the pooled operating reserve. Replace these percentages with property-specific quotations before making a decision.",
        "platform": "Platform and payment costs",
        "cleaning": "Cleaning and linen",
        "utilities": "Utilities and internet",
        "management": "Management and guest support",
        "maintenance": "Maintenance and wear reserve",
        "total_reserve": "Total operating reserve",
        "not_included": "Not included",
        "taxes_permits": "Income tax, permit fees, financing costs and extraordinary repairs are not included.",
        "contact_on_whatsapp": "Ask on WhatsApp",
        "schedule_visit": "Open listing details",
        "open_map": "Open property map",
        "print_report": "Print / Save PDF",
        "view_original": "View original listing",
        "whatsapp_message": "Hello, I would like more information about this investment property.",
        "studio": "Studio",
        "apartment": "Apartment",
        "bath": "bath",
        "bed": "bed",
        "guests": "guests",
        "furnished_unit": "Furnished",
        "expo_demand": "Expo demand",
        "retail_transport": "Retail and transport",
        "medical_demand": "Medical demand",
        "transit": "Transit",
        "exact_comp_support": "nearby close-spec comparisons support the quoted-price model.",
        "thin_comp_support": "The comparison set is thin; refresh the Airbnb data before treating the figures as final underwriting.",
        "small_unit_fit": "The small-unit format fits solo visitors, couples, business stays and patient-family overflow.",
        "floor_position": "Floor position",
        "tuyap_demand_title": "TÜYAP calendar demand windows",
        "anchor_demand_title": "Strategic demand anchors",
        "tuyap_demand_intro": "The official fair calendar shows repeated multi-day demand windows across the exhibition season.",
        "anchor_demand_intro": "Nearby anchors help test whether comparison pricing is supported by repeatable guest traffic.",
        "strong_thesis": "The quoted short-stay base case is strong relative to deployed capital, but it remains conditional rather than guaranteed.",
        "workable_thesis": "The quoted short-stay base case is workable, with purchase negotiation and operating quality still important.",
        "cautious_thesis": "The current short-stay case needs caution or a lower purchase price.",
        "usable_comps": "The current comparison set provides a usable starting point.",
        "thin_comps": "Comparison confidence is thin; refresh the data before committing.",
        "legal_caveat": "Legal eligibility remains unverified.",
        "legal_verified": "The record marks eligibility as verified, subject to document review.",
        "no_comps": "No comparison records are currently available.",
    },
    "fr": {
        "investment_portfolio": "Dossier d’investissement",
        "special_portfolio": "Dossier spécial du bien",
        "purchase": "Prix d’achat",
        "quoted_30_night_median": "Prix médian affiché pour 30 nuits",
        "conditional_roi": "Rendement annuel conditionnel",
        "estimated_before_tax": "Estimation avant impôts",
        "conditional": "Conditionnel",
        "short_term_status": "Éligibilité à la location de courte durée",
        "unverified": "Non vérifiée",
        "verified": "Vérifiée",
        "restricted": "Restreinte",
        "not_permitted": "Non autorisée",
        "permit_unverified_note": "L’éligibilité à la location touristique et le règlement de gestion de l’immeuble n’ont pas été vérifiés. Considérez chaque rendement de courte durée comme un scénario conditionnel jusqu’à obtention d’une confirmation écrite.",
        "permit_verified_note": "La fiche du bien indique que l’éligibilité à la location de courte durée est vérifiée. Consultez néanmoins le permis et les documents de l’immeuble avant de vous fier au scénario.",
        "permit_restricted_note": "La location de courte durée peut être soumise à des restrictions liées à l’immeuble, au règlement de gestion, au permis ou à l’exploitation. Confirmez les conditions exactes avant de vous fier au scénario.",
        "permit_not_permitted_note": "La fiche du bien indique que la location de courte durée n’est pas autorisée. Utilisez le scénario locatif classique pour l’analyse.",
        "map_intelligence": "Analyse cartographique",
        "airbnb_comps_title": "Comparaisons Airbnb autour du bien",
        "why_location_matters": "Pourquoi cet emplacement compte",
        "fresh_evidence": "Données Airbnb récentes",
        "rental_set": "Échantillon de prix affichés sur 30 nuits",
        "rental_set_intro": "Les biens aux caractéristiques proches sont séparés du contexte local plus large. Les prix affichés constituent des éléments de comparaison, et non une garantie d’occupation ou de revenu récurrent.",
        "underwriting_market": "Marché de référence",
        "comp_count": "Nombre de comparables principaux",
        "exact_matches": "Comparables proches du même type",
        "availability_checked": "Disponibilité vérifiée",
        "reviewed_comps": "Comparables avec avis",
        "confidence": "Niveau de confiance",
        "high": "Élevé",
        "medium": "Moyen",
        "low": "Faible",
        "price_band": "P25 / Médiane / P75",
        "comp_range": "Fourchette affichée",
        "same_spec": "Caractéristiques proches",
        "context_comp": "Contexte plus large",
        "available": "Disponible",
        "unavailable": "Indisponible",
        "availability_unchecked": "Disponibilité non vérifiée",
        "guest_favorite": "Coup de cœur voyageurs",
        "rare_find": "Bien rare",
        "new_unrated": "nouveau / sans note",
        "rating": "note",
        "listing_reviews": "avis sur l’annonce",
        "host_reviews": "avis sur l’hôte",
        "years_hosting": "ans d’expérience",
        "verified_host": "Vérifié",
        "days_30": "30 nuits",
        "per_night": "/nuit",
        "previous_comp": "Comparable Airbnb précédent",
        "next_comp": "Comparable Airbnb suivant",
        "swipe_comps": "Faites défiler les comparables",
        "strategic_demand": "Demande stratégique",
        "calendar_source": "Source du calendrier : calendrier officiel des salons TÜYAP, vérifié le 4 juillet 2026.",
        "rentability": "Scénarios de rendement",
        "yield_scenarios": "Scénarios de rendement sans financement",
        "scenario_intro": "Les calculs incluent le prix d’achat, l’ameublement et une réserve de frais de clôture. Les chiffres de courte durée appliquent une réserve d’exploitation globale et restent conditionnels à l’éligibilité légale, à l’occupation réelle et à la qualité de gestion.",
        "long_term_fallback": "Location classique",
        "airbnb_base": "Base courte durée",
        "operator_upside": "Potentiel avec opérateur",
        "estimated_monthly_net": "Net mensuel estimé",
        "gross_rent": "Loyer brut",
        "gross_revenue": "Revenu brut affiché",
        "annual_net_roi": "Rendement annuel estimé",
        "investment_read": "Lecture de l’investissement",
        "operating_assumptions": "Hypothèses de réserve d’exploitation",
        "operating_assumptions_intro": "Répartition indicative de la réserve d’exploitation globale. Remplacez ces pourcentages par des devis propres au bien avant toute décision.",
        "platform": "Plateforme et paiements",
        "cleaning": "Ménage et linge",
        "utilities": "Charges, internet et énergie",
        "management": "Gestion et assistance voyageurs",
        "maintenance": "Entretien et usure",
        "total_reserve": "Réserve d’exploitation totale",
        "not_included": "Non inclus",
        "taxes_permits": "Les impôts sur le revenu, frais de permis, coûts de financement et réparations exceptionnelles ne sont pas inclus.",
        "contact_on_whatsapp": "Demander sur WhatsApp",
        "schedule_visit": "Voir la fiche du bien",
        "open_map": "Ouvrir la carte du bien",
        "print_report": "Imprimer / Enregistrer en PDF",
        "view_original": "Voir l’annonce d’origine",
        "whatsapp_message": "Bonjour, je souhaite obtenir plus d’informations sur ce bien d’investissement.",
        "studio": "Studio",
        "apartment": "Appartement",
        "bath": "salle de bain",
        "bed": "lit",
        "guests": "voyageurs",
        "furnished_unit": "Meublé",
        "expo_demand": "Demande liée aux salons",
        "retail_transport": "Commerce et transport",
        "medical_demand": "Demande médicale",
        "transit": "Transport",
        "exact_comp_support": "comparables proches soutiennent le modèle de prix affichés.",
        "thin_comp_support": "L’échantillon est limité ; actualisez les données Airbnb avant de considérer ces chiffres comme une analyse définitive.",
        "small_unit_fit": "Le format compact convient aux voyageurs seuls, couples, déplacements professionnels et proches de patients.",
        "floor_position": "Position dans l’immeuble",
        "tuyap_demand_title": "Fenêtres de demande du calendrier TÜYAP",
        "anchor_demand_title": "Pôles de demande stratégiques",
        "tuyap_demand_intro": "Le calendrier officiel présente des périodes répétées de demande sur plusieurs jours pendant la saison des salons.",
        "anchor_demand_intro": "Les pôles voisins permettent d’évaluer si les prix comparables sont soutenus par un trafic régulier de voyageurs.",
        "strong_thesis": "Le scénario de courte durée affiché est fort par rapport au capital engagé, mais il reste conditionnel et non garanti.",
        "workable_thesis": "Le scénario de courte durée affiché est exploitable, mais la négociation du prix et la qualité de gestion restent importantes.",
        "cautious_thesis": "Le scénario actuel de courte durée exige de la prudence ou un prix d’achat plus bas.",
        "usable_comps": "L’échantillon actuel constitue un point de départ exploitable.",
        "thin_comps": "La confiance dans les comparables est faible ; actualisez les données avant de vous engager.",
        "legal_caveat": "L’éligibilité légale reste non vérifiée.",
        "legal_verified": "La fiche indique une éligibilité vérifiée, sous réserve de contrôler les documents.",
        "no_comps": "Aucun comparable n’est actuellement disponible.",
    },
}

CATEGORY_KEYS = {
    "Expo demand": "expo_demand",
    "Retail and transport": "retail_transport",
    "Medical demand": "medical_demand",
    "Transit": "transit",
}

STATUS_COPY = {
    "unverified": ("unverified", "permit_unverified_note", "warning"),
    "verified": ("verified", "permit_verified_note", "success"),
    "restricted": ("restricted", "permit_restricted_note", "warning"),
    "not_permitted": ("not_permitted", "permit_not_permitted_note", "danger"),
}


def _language_code(language=None):
    raw = language or get_language() or "en"
    return str(raw).lower().split("-")[0].split("_")[0]


def portfolio_copy_for_language(language=None):
    return COPY.get(_language_code(language), COPY["en"])


def _as_int(value, default=0):
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return default


def _portfolio_config(listing):
    source = getattr(listing, "source_search_context", None) or {}
    config = source.get("portfolio", {}) if isinstance(source, dict) else {}
    return config if isinstance(config, dict) else {}


def _operating_breakdown(config):
    supplied = config.get("operating_cost_breakdown", {})
    supplied = supplied if isinstance(supplied, dict) else {}
    defaults = {
        "platform": 4,
        "cleaning": 8,
        "utilities": 6,
        "management": 8,
        "maintenance": 4,
    }
    return [
        {"key": key, "percent": _as_int(supplied.get(key), default)}
        for key, default in defaults.items()
    ]


def build_portfolio_meta(listing, comps=None, rentability=None, anchors=None, language=None):
    copy = portfolio_copy_for_language(language)
    comps = list(comps or [])
    anchors = list(anchors or [])
    rentability = rentability or {}
    config = _portfolio_config(listing)

    exact_count = sum(1 for item in comps if item.get("is_same_spec"))
    availability_checked = sum(1 for item in comps if item.get("is_available") is not None)
    available_count = sum(1 for item in comps if item.get("is_available") is True)
    reviewed_count = sum(1 for item in comps if _as_int(item.get("reviews")) > 0)

    if exact_count >= 5 and availability_checked >= 3 and reviewed_count >= 3:
        confidence_key = "high"
        confidence_class = "success"
    elif exact_count >= 3:
        confidence_key = "medium"
        confidence_class = "warning"
    else:
        confidence_key = "low"
        confidence_class = "danger"

    raw_status = str(config.get("short_term_rental_status", "unverified")).strip().lower().replace("-", "_").replace(" ", "_")
    status = raw_status if raw_status in STATUS_COPY else "unverified"
    status_label_key, default_note_key, status_class = STATUS_COPY[status]
    permit_note = str(config.get("short_term_rental_note") or copy[default_note_key]).strip()

    room = getattr(listing, "rooms_text", None) or getattr(listing, "bedrooms", None) or copy["furnished_unit"]
    primary_anchor = anchors[0] if anchors else None
    if primary_anchor:
        if _language_code(language) == "fr":
            hero_summary = (
                f"Unité d’investissement {room} à proximité de {primary_anchor.get('title', '')}, "
                "évaluée à partir de prix affichés sur 30 nuits pour des biens comparables proches."
            )
        else:
            hero_summary = (
                f"{room} investment unit near {primary_anchor.get('title', '')}, checked against nearby "
                "quoted 30-night prices for comparable stays."
            )
    else:
        if _language_code(language) == "fr":
            hero_summary = (
                f"Unité d’investissement {room}, évaluée à partir de prix affichés sur 30 nuits "
                "et de la demande locative meublée locale."
            )
        else:
            hero_summary = (
                f"{room} investment unit checked against quoted 30-night prices and local furnished-rental demand."
            )

    location_bullets = []
    for anchor in anchors[:3]:
        category_key = CATEGORY_KEYS.get(anchor.get("category"), "transit")
        if _language_code(language) == "fr":
            location_bullets.append(
                f"À {anchor.get('distance_km')} km de {anchor.get('title')} ({copy[category_key]})."
            )
        else:
            location_bullets.append(
                f"{anchor.get('distance_km')} km from {anchor.get('title')} ({copy[category_key]})."
            )

    if exact_count:
        location_bullets.append(f"{exact_count} {copy['exact_comp_support']}")
    elif comps:
        location_bullets.append(copy["thin_comp_support"])
    else:
        location_bullets.append(copy["no_comps"])

    room_raw = str(room).lower()
    if "1+0" in room_raw or "studio" in room_raw or "1+1" in room_raw:
        location_bullets.append(copy["small_unit_fit"])

    floor_number = getattr(listing, "floor_number", None)
    floors_total = getattr(listing, "floors_total", None)
    if floor_number or floors_total:
        location_bullets.append(
            f"{copy['floor_position']}: {floor_number or '—'} / {floors_total or '—'}."
        )

    has_tuyap = any(item.get("key") == "tuyap" for item in anchors)
    demand_title = copy["tuyap_demand_title"] if has_tuyap else copy["anchor_demand_title"]
    demand_intro = copy["tuyap_demand_intro"] if has_tuyap else copy["anchor_demand_intro"]

    roi = float(rentability.get("airbnb_roi") or 0)
    if roi >= 20:
        thesis = copy["strong_thesis"]
    elif roi >= 12:
        thesis = copy["workable_thesis"]
    else:
        thesis = copy["cautious_thesis"]
    comp_read = copy["usable_comps"] if exact_count >= 3 else copy["thin_comps"]
    legal_read = copy["legal_verified"] if status == "verified" else copy["legal_caveat"]

    operating_rate = _as_int(float(rentability.get("operating_cost_rate") or 0.30) * 100, 30)
    return {
        "copy": copy,
        "hero_summary": hero_summary,
        "location_bullets": location_bullets[:5],
        "exact_count": exact_count,
        "availability_checked": availability_checked,
        "available_count": available_count,
        "reviewed_count": reviewed_count,
        "confidence_key": confidence_key,
        "confidence_label": copy[confidence_key],
        "confidence_class": confidence_class,
        "permit_status": status,
        "permit_label": copy[status_label_key],
        "permit_note": permit_note,
        "permit_class": status_class,
        "demand_title": demand_title,
        "demand_intro": demand_intro,
        "calendar_source": copy["calendar_source"],
        "investment_read": " ".join((thesis, comp_read, legal_read)),
        "operating_rate": operating_rate,
        "operating_breakdown": _operating_breakdown(config),
        "is_short_stay_conditional": status != "verified",
    }


@register.simple_tag
def portfolio_copy():
    return portfolio_copy_for_language()


@register.simple_tag
def portfolio_meta(listing, comps=None, rentability=None, anchors=None):
    return build_portfolio_meta(listing, comps, rentability, anchors)


@register.filter
def whatsapp_number(value):
    digits = "".join(character for character in str(value or "") if character.isdigit())
    if digits.startswith("00"):
        digits = digits[2:]
    if len(digits) == 11 and digits.startswith("0"):
        digits = "90" + digits[1:]
    return digits


@register.filter
def query_escape(value):
    return quote_plus(str(value or ""))
