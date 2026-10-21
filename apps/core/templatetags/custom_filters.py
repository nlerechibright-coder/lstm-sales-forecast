from django import template

register = template.Library()


@register.filter
def dict_get(d, key):
    """Get a value from a dict by key, returning None if not found."""
    if not d:
        return None
    return d.get(key)


@register.filter
def get_item(d, key):
    """Get a value from a dict by key (alternative name)."""
    if not d:
        return None
    return d.get(key)


@register.filter
def sub(value, arg):
    """Subtract arg from value."""
    try:
        return float(value) - float(arg)
    except (ValueError, TypeError):
        return 0