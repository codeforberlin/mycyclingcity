# Information Hub i18n Documentation

## Overview

The Information Hub is a global UI component that provides a unified information center accessible from both Map View and Ranking View. All user-facing strings are fully internationalized using Django's i18n framework.

## Translation Keys

The following strings are translatable in the Information Hub:

### Button & Modal
- `"Information"` - Button tooltip
- `"Close"` - Close button tooltip

### Header
- `"Version"` - Version label

### FAQ Section
- `"Frequently Asked Questions"` - Section title
- `"How does the live map work?"` - FAQ question 1
- `"The live map shows the current positions of all active cyclists in real-time. You can filter between different routes and groups to customize the view."` - FAQ answer 1
- `"What does the ranking show?"` - FAQ question 2
- `"The ranking shows the current mileage of all groups and cyclists, sorted by distance traveled. You can filter by specific groups."` - FAQ answer 2
- `"How does the map update?"` - FAQ question 3
- `"The map updates automatically every 20 seconds. Positions and mileage are updated in real-time as soon as new data is available."` - FAQ answer 3
- `"Open Full Documentation"` - Documentation link text

### Language Section
- `"Language"` - Language section title

### Footer
- `"Legal Notice"` - Impressum link
- `"Privacy Policy"` - Privacy policy link

## Adding a New Language

To add support for a new language to the Information Hub:

1. **Add language to settings.py**:
   ```python
   LANGUAGES = [
       ('en', _('English')),
       ('de', _('Deutsch')),
       ('fr', _('Français')),  # Example: Add French
   ]
   ```

2. **Generate translation files**:
   ```bash
   python manage.py makemessages -l fr
   ```

3. **Translate strings**:
   Edit `locale/fr/LC_MESSAGES/django.po` and add translations for all strings.

4. **Compile translations**:
   ```bash
   python manage.py compilemessages
   ```

5. **Restart the server**:
   The new language will be available in the language switcher.

## Language Switcher Integration

The language switcher in the Information Hub modal:
- Uses Django's `set_language` view (POST request, CSRF-protected)
- Automatically reloads the page with the new language prefix
- Updates all labels, headers, and data formats immediately
- Works globally across Map View and Ranking View

## Number Formatting

The `format_km_de` filter automatically adapts to the active language:
- **German (de)**: `1.234,567 km` (dot thousands, comma decimal)
- **English (en)**: `1,234.567 km` (comma thousands, dot decimal)

The filter reads the current `LANGUAGE_CODE` from the request context and formats numbers accordingly.

## Files to Update When Adding Translations

- `map/templates/map/partials/info_modal.html` - Main modal template
- `templates/partials/info_hub.html` - Global wrapper
- `locale/<lang_code>/LC_MESSAGES/django.po` - Translation files

## Testing Translations

1. Switch language using the Information Hub modal
2. Verify all strings are translated
3. Check number formatting (should match language)
4. Test in both Map View and Ranking View


