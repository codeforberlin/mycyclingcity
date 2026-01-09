/**
 * Timezone Converter - Converts UTC datetime strings to browser's local timezone
 * 
 * This script automatically finds and converts all datetime elements
 * that have data-utc-datetime attributes or are in ISO 8601 format.
 */

(function() {
    'use strict';

    /**
     * Convert UTC datetime string to local timezone and format it
     * @param {string} utcString - ISO 8601 datetime string (UTC)
     * @param {string} format - Format string (default: 'd.m.Y H:i')
     * @returns {string} Formatted datetime string in local timezone
     */
    function convertUTCToLocal(utcString, format) {
        if (!utcString) return '';
        
        try {
            const date = new Date(utcString);
            if (isNaN(date.getTime())) return utcString; // Invalid date, return original
            
            // Default format: 'd.m.Y H:i' (e.g., "27.12.2024 14:30")
            if (!format || format === 'd.m.Y H:i') {
                const day = String(date.getDate()).padStart(2, '0');
                const month = String(date.getMonth() + 1).padStart(2, '0');
                const year = date.getFullYear();
                const hours = String(date.getHours()).padStart(2, '0');
                const minutes = String(date.getMinutes()).padStart(2, '0');
                return `${day}.${month}.${year} ${hours}:${minutes}`;
            }
            
            // Handle other formats if needed
            return date.toLocaleString('de-DE', {
                year: 'numeric',
                month: '2-digit',
                day: '2-digit',
                hour: '2-digit',
                minute: '2-digit',
                timeZone: Intl.DateTimeFormat().resolvedOptions().timeZone
            });
        } catch (e) {
            console.warn('Error converting datetime:', utcString, e);
            return utcString;
        }
    }

    /**
     * Convert all datetime elements on the page
     */
    function convertAllDatetimes() {
        // Find all elements with data-utc-datetime attribute
        document.querySelectorAll('[data-utc-datetime]').forEach(function(el) {
            const utcString = el.getAttribute('data-utc-datetime');
            const format = el.getAttribute('data-datetime-format') || 'd.m.Y H:i';
            const converted = convertUTCToLocal(utcString, format);
            if (converted) {
                el.textContent = converted;
                el.removeAttribute('data-utc-datetime'); // Prevent double conversion
            }
        });

        // Find all elements with class 'utc-datetime'
        document.querySelectorAll('.utc-datetime').forEach(function(el) {
            const utcString = el.textContent.trim();
            const format = el.getAttribute('data-format') || 'd.m.Y H:i';
            const converted = convertUTCToLocal(utcString, format);
            if (converted && converted !== utcString) {
                el.textContent = converted;
                el.classList.remove('utc-datetime'); // Prevent double conversion
            }
        });
    }

    // Run on DOMContentLoaded
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', convertAllDatetimes);
    } else {
        convertAllDatetimes();
    }

    // Also run after HTMX swaps (for dynamic content)
    if (typeof htmx !== 'undefined') {
        document.body.addEventListener('htmx:afterSwap', convertAllDatetimes);
        document.body.addEventListener('htmx:afterSettle', convertAllDatetimes);
    }

    // Export function for manual use
    window.convertUTCToLocal = convertUTCToLocal;
    window.convertAllDatetimes = convertAllDatetimes;
})();

