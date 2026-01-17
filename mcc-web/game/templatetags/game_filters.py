"""
Template filters for the game app.

This module provides filters that ensure CSS-compatible number formatting,
always using dots (.) as decimal separators regardless of locale settings.
"""
from django import template

register = template.Library()


@register.filter
def css_number(value, decimals=1):
    """
    Format a number for use in CSS values, always using dot as decimal separator.
    
    This filter ensures that numeric values used in CSS (like width, height, etc.)
    are always formatted with a dot (.) as decimal separator, regardless of the
    current locale setting. This prevents issues where German locale would use
    commas (,) which CSS doesn't accept.
    
    Args:
        value: Numeric value to format
        decimals: Number of decimal places (default: 1)
    
    Returns:
        String representation of the number with dot as decimal separator
    
    Example:
        {{ 90.5|css_number:1 }}  # Returns "90.5" (never "90,5")
        {{ progress|css_number:2 }}  # Returns "90.50" (never "90,50")
    """
    if value is None:
        return "0"
    
    try:
        num = float(value)
        # Format with specified decimals, always using dot
        formatted = f"{num:.{decimals}f}"
        # Ensure dot is used (replace comma if locale added one)
        return formatted.replace(',', '.')
    except (ValueError, TypeError):
        return "0"


@register.filter
def css_percent(value, decimals=1):
    """
    Format a percentage value for use in CSS, always using dot as decimal separator.
    
    Similar to css_number, but specifically for percentage values.
    
    Args:
        value: Numeric value (0-100) to format as percentage
        decimals: Number of decimal places (default: 1)
    
    Returns:
        String representation with dot as decimal separator
    
    Example:
        {{ 90.5|css_percent:1 }}  # Returns "90.5" (for width: 90.5%)
    """
    return css_number(value, decimals)
