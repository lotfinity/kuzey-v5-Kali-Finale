from django.db import OperationalError, ProgrammingError

from .models import CurrencySettings


DEFAULT_CURRENCY_RATES = {
    'TRY': 1.0,
    'USD': 0.021661,
    'EUR': 0.018768,
    'DZD': 5.0,
}


def currency_settings(request):
    try:
        settings = CurrencySettings.load()
    except (OperationalError, ProgrammingError):
        return {
            'currency_rates': DEFAULT_CURRENCY_RATES,
            'currency_default': 'TRY',
        }

    return {
        'currency_rates': {
            'TRY': 1.0,
            'USD': float(settings.try_to_usd),
            'EUR': float(settings.try_to_eur),
            'DZD': float(settings.try_to_dzd),
        },
        'currency_default': 'TRY',
    }
