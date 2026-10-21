from django import template
from django.contrib.humanize.templatetags.humanize import intcomma

register = template.Library()


@register.filter
def sub(value, arg):
    """Subtract arg from value."""
    try:
        return float(value) - float(arg)
    except (ValueError, TypeError):
        return value


@register.filter
def naira(value):
    """Format a number as Nigerian Naira with commas and 2 decimal places."""
    if value is None or value == '':
        return '₦0.00'
    try:
        val = float(value)
        # Format with 2 decimal places first, then add commas
        formatted = f'{val:,.2f}'
        return f'₦{formatted}'
    except (ValueError, TypeError):
        return '₦0.00'


@register.filter
def naira_short(value):
    """Short Naira format (K for thousands, M for millions)."""
    if value is None:
        return '₦0'
    try:
        val = float(value)
        if val >= 1_000_000_000:
            return f'₦{val/1_000_000_000:.1f}B'
        elif val >= 1_000_000:
            return f'₦{val/1_000_000:.1f}M'
        elif val >= 1_000:
            return f'₦{val/1_000:.1f}K'
        else:
            return f'₦{val:.0f}'
    except (ValueError, TypeError):
        return '₦0'


@register.filter
def percentage_change(value):
    """Format a percentage change with sign."""
    if value is None:
        return '0.0%'
    try:
        val = float(value)
        sign = '+' if val > 0 else ''
        return f'{sign}{val:.1f}%'
    except (ValueError, TypeError):
        return '0.0%'


@register.filter
def dict_get(dictionary, key):
    """Get a value from a dictionary by key."""
    if dictionary is None:
        return None
    try:
        return dictionary.get(key)
    except AttributeError:
        return None


@register.filter
def get_item(dictionary, key):
    """Get a value from a dictionary by key (alias for dict_get)."""
    if dictionary is None:
        return None
    try:
        return dictionary.get(key)
    except AttributeError:
        return None