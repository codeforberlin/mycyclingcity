# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    leaderboard_filters.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

#
"""
Project: MyCyclingCity
Generation: AI-based

Template tags for leaderboard app.
Provides formatting functions for leaderboard-related templates.
"""

from typing import Any, Dict, Optional
from django import template
from django.utils import translation
from django.conf import settings

register = template.Library()


@register.filter
def get_item(dictionary: dict, key: str) -> str:
    """
    Template filter to access dictionary items by key.
    
    Args:
        dictionary: Dictionary to access.
        key: Key to look up.
    
    Returns:
        Value from dictionary or default gray color if key not found.
    """
    if dictionary is None:
        return None
    return dictionary.get(key, '#6b7280')  # Default to gray-500 if key not found


def _format_number_by_language(value: float, decimals: int, language_code: str = None) -> str:
    """
    Internal helper function to format number based on language.
    
    Args:
        value: Numeric value to format.
        decimals: Number of decimal places.
        language_code: Optional language code override.
    
    Returns:
        Formatted string with appropriate separators.
    """
    if value is None:
        value = 0
    try:
        num = float(value)
        fixed = f"{num:.{decimals}f}"
        parts = fixed.split('.')
        integer_str = parts[0]
        decimal_part = parts[1] if len(parts) > 1 else ''
        
        # Get current language
        if language_code is None:
            current_language = translation.get_language()
            if not current_language:
                current_language = getattr(settings, 'LANGUAGE_CODE', 'de')
        else:
            current_language = language_code
            
        # Normalize language code (e.g., 'en-us' -> 'en', 'de-de' -> 'de')
        if current_language:
            lang_code = str(current_language).split('-')[0].lower()
        else:
            lang_code = 'de'
        is_german = (lang_code == 'de')
        
        if is_german:
            # German format: dot for thousands, comma for decimal
            integer_with_separators = ''
            for i, char in enumerate(reversed(integer_str)):
                if i > 0 and i % 3 == 0:
                    integer_with_separators = '.' + integer_with_separators
                integer_with_separators = char + integer_with_separators
            return integer_with_separators + (',' + decimal_part if decimal_part else '')
        else:
            # English format: comma for thousands, dot for decimal
            integer_with_separators = ''
            for i, char in enumerate(reversed(integer_str)):
                if i > 0 and i % 3 == 0:
                    integer_with_separators = ',' + integer_with_separators
                integer_with_separators = char + integer_with_separators
            return integer_with_separators + ('.' + decimal_part if decimal_part else '')
    except (ValueError, TypeError):
        if language_code is None:
            current_language = translation.get_language()
            if not current_language:
                current_language = getattr(settings, 'LANGUAGE_CODE', 'de')
        else:
            current_language = language_code
        lang_code = str(current_language).split('-')[0].lower() if current_language else 'de'
        is_german = lang_code == 'de'
        decimal_sep = ',' if is_german else '.'
        return '0' + (decimal_sep + '0' * decimals if decimals > 0 else '')


@register.filter
def format_km_de(value: float, decimals: int = 3) -> str:
    """
    Format number based on current language.
    
    German format: dot thousands, comma decimal (e.g., 1.234,567)
    English format: comma thousands, dot decimal (e.g., 1,234.567)
    
    Args:
        value: Numeric value to format.
        decimals: Number of decimal places (default: 3).
    
    Returns:
        Formatted string with appropriate separators.
    """
    # Try to get language from translation context
    language_code = translation.get_language()
    if not language_code:
        language_code = getattr(settings, 'LANGUAGE_CODE', 'de')
    return _format_number_by_language(value, decimals, language_code)


@register.simple_tag(takes_context=True)
def format_km_de_tag(context: dict, value: float, decimals: int = 3) -> str:
    """
    Format number based on language from request context.
    
    Args:
        context: Template context dictionary.
        value: Numeric value to format.
        decimals: Number of decimal places (default: 3).
    
    Returns:
        Formatted string with appropriate separators.
    """
    # Handle None values
    if value is None:
        value = 0
    
    # Try to get language from multiple sources
    language_code = None
    request = context.get('request')
    
    # Method 1: Try to get from i18n context processor (most reliable)
    language_code = context.get('LANGUAGE_CODE')
    
    # Method 2: Try to get from request object (set by LocaleMiddleware)
    if not language_code and request:
        language_code = getattr(request, 'LANGUAGE_CODE', None)
    
    # Method 3: Try to extract from URL path (e.g., /en/... or /de/...)
    if not language_code and request:
        path = getattr(request, 'path', '')
        # Check if path starts with language code
        for lang_code, _ in getattr(settings, 'LANGUAGES', [('en', 'English'), ('de', 'Deutsch')]):
            if path.startswith(f'/{lang_code}/') or path == f'/{lang_code}':
                language_code = lang_code
                break
    
    # Method 4: Fall back to translation.get_language()
    if not language_code:
        language_code = translation.get_language()
    
    # Method 5: Final fallback to settings
    if not language_code:
        language_code = getattr(settings, 'LANGUAGE_CODE', 'de')
    
    # Ensure we have a valid language code
    if not language_code:
        language_code = 'de'
    
    # Normalize language code (e.g., 'en-us' -> 'en')
    if language_code:
        language_code = str(language_code).split('-')[0].lower()
    
    return _format_number_by_language(value, decimals, language_code)

