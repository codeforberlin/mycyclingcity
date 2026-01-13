# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    utils.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

#
"""
Project: MyCyclingCity
Generation: AI-based

Shared utility functions for MyCyclingCity applications.
"""

from typing import Optional
from django.utils import translation
from django.conf import settings


def format_km_de(value: Optional[float], decimals: int = 3, language_code: Optional[str] = None) -> str:
    """
    Format number based on language: German format (dot thousands, comma decimal) 
    or English format (comma thousands, dot decimal).
    
    Args:
        value: The numeric value to format. Can be None.
        decimals: Number of decimal places (default: 3).
        language_code: Optional language code override. If None, uses current language.
    
    Returns:
        Formatted string with appropriate thousands and decimal separators.
    
    Examples:
        >>> format_km_de(1234.567, 3, 'de')
        '1.234,567'
        >>> format_km_de(1234.567, 3, 'en')
        '1,234.567'
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


