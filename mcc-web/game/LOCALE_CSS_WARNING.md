# ⚠️ WICHTIG: Locale-Probleme mit CSS-Werten

## Problem

Django's `floatformat` Filter verwendet die aktuelle Locale-Einstellung für die Formatierung von Dezimalzahlen. In der deutschen Locale werden **Kommas (`,`)** als Dezimaltrennzeichen verwendet, während CSS nur **Punkte (`.`)** akzeptiert.

### Beispiel des Problems

```django
{# FALSCH: Kann "90,0%" erzeugen, was CSS nicht akzeptiert #}
<div style="width: {{ progress|floatformat:1 }}%">
```

Wenn die deutsche Locale aktiv ist, wird dies zu `width: 90,0%`, was CSS ignoriert oder falsch interpretiert.

## Lösung

### 1. Template-Filter verwenden (Empfohlen)

Verwenden Sie die speziellen Template-Filter `css_number` oder `css_percent`:

```django
{% load game_filters %}

{# RICHTIG: Immer Punkt als Dezimaltrennzeichen #}
<div style="width: {{ progress|css_percent:1 }}%">
```

### 2. Utility-Funktion in Views verwenden

Für Werte, die in Views berechnet werden:

```python
from game.views import format_css_number

# In der View
result['progress_percent_str'] = format_css_number(progress_percent, decimals=1)

# Im Template
<div style="width: {{ result.progress_percent_str }}%">
```

## Verfügbare Tools

### Template-Filter

- `css_number(value, decimals=1)`: Formatiert eine Zahl für CSS-Werte
- `css_percent(value, decimals=1)`: Formatiert eine Prozentzahl für CSS-Werte

### Python-Funktion

- `format_css_number(value, decimals=1)`: Utility-Funktion in `game/views.py`

## Wann verwenden?

**IMMER verwenden für:**
- CSS `style` Attribute mit numerischen Werten
- `width`, `height`, `margin`, `padding`, etc. mit Dezimalzahlen
- CSS-Variablen mit numerischen Werten
- Inline-Styles in Templates

**NICHT verwenden für:**
- Anzeige von Zahlen im Text (dort ist Locale-Formatierung erwünscht)
- `floatformat` ist für Anzeige-Zwecke in Ordnung

## Beispiele

### ❌ FALSCH

```django
<div style="width: {{ progress|floatformat:1 }}%">
<div style="height: {{ height|floatformat:2 }}px">
```

### ✅ RICHTIG

```django
{% load game_filters %}
<div style="width: {{ progress|css_percent:1 }}%">
<div style="height: {{ height|css_number:2 }}px">
```

Oder in der View:

```python
context['height_str'] = format_css_number(height, decimals=2)
```

```django
<div style="height: {{ height_str }}px">
```

## Code-Review Checkliste

Bei Code-Reviews immer prüfen:

- [ ] Werden numerische Werte in CSS `style` Attributen verwendet?
- [ ] Wird `floatformat` in CSS-Kontexten verwendet?
- [ ] Wenn ja: Wird `css_number`/`css_percent` oder `format_css_number()` verwendet?

## Weitere Informationen

- Template-Filter: `game/templatetags/game_filters.py`
- Utility-Funktion: `game/views.py` → `format_css_number()`
