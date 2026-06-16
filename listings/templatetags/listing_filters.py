from django import template
from django.utils.timesince import timesince
from django.utils.timezone import now
from datetime import date

register = template.Library()


@register.filter
def days_ago(value):
    if not value:
        return ''
    if isinstance(value, str):
        return value
    delta = now().date() - value if isinstance(value, date) else now().date() - value.date()
    days = delta.days
    if days < 0:
        return ''
    if days == 0:
        return 'Today'
    if days == 1:
        return 'Yesterday'
    if days < 30:
        return f'{days} days ago'
    weeks = days // 7
    if weeks < 5:
        return f'{weeks} week{"s" if weeks > 1 else ""} ago'
    months = days // 30
    if months < 12:
        return f'{months} month{"s" if months > 1 else ""} ago'
    years = days // 365
    return f'{years} year{"s" if years > 1 else ""} ago'
