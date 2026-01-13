/**
 * Copyright (c) 2026 SAI-Lab / MyCyclingCity
 * SPDX-License-Identifier: AGPL-3.0-or-later
 *
 * @file    milestone_delete_warning.js
 * @author  Roland Rutz
 * @note    This code was developed with the assistance of AI (LLMs).
 */

// Hide delete buttons for milestones that are used in trips
(function($) {
    $(document).ready(function() {
        // Function to hide delete buttons for milestones with track_id
        function hideDeleteButtons() {
            // Find all rows in the milestone changelist
            $('table#result_list tbody tr').each(function() {
                var $row = $(this);
                // Check if this row has a warning column indicating it's used in a trip
                var $warningCell = $row.find('td.field-deletion_warning');
                if ($warningCell.length > 0 && $warningCell.text().trim() !== '') {
                    // This milestone is used in a trip, hide the delete checkbox
                    var $checkbox = $row.find('td.action-checkbox input[type="checkbox"]');
                    if ($checkbox.length > 0) {
                        $checkbox.closest('td').hide();
                    }
                    // Also hide the delete link in the action column if present
                    var $actionLinks = $row.find('td a');
                    $actionLinks.each(function() {
                        if ($(this).attr('href') && $(this).attr('href').includes('/delete/')) {
                            $(this).closest('td').hide();
                        }
                    });
                }
            });
            
            // Hide bulk delete action button if all selected items cannot be deleted
            var $selectedCheckboxes = $('table#result_list tbody tr input[type="checkbox"]:checked');
            if ($selectedCheckboxes.length > 0) {
                var allCannotDelete = true;
                $selectedCheckboxes.each(function() {
                    var $row = $(this).closest('tr');
                    var $warningCell = $row.find('td.field-deletion_warning');
                    if ($warningCell.length === 0 || $warningCell.text().trim() === '') {
                        allCannotDelete = false;
                        return false; // break
                    }
                });
                if (allCannotDelete) {
                    $('.actions select[name="action"] option[value="delete_selected"]').hide();
                }
            }
        }
        
        // Run on page load
        hideDeleteButtons();
        
        // Run after HTMX or other dynamic updates
        $(document).on('DOMNodeInserted', function() {
            hideDeleteButtons();
        });
        
        // Also use MutationObserver for better performance
        if (window.MutationObserver) {
            var observer = new MutationObserver(function(mutations) {
                hideDeleteButtons();
            });
            observer.observe(document.body, {
                childList: true,
                subtree: true
            });
        }
    });
})(django.jQuery);

