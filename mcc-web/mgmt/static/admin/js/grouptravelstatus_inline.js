/**
 * Copyright (c) 2026 SAI-Lab / MyCyclingCity
 * SPDX-License-Identifier: AGPL-3.0-or-later
 *
 * @file    grouptravelstatus_inline.js
 * @author  Roland Rutz
 * @note    This code was developed with the assistance of AI (LLMs).
 */

/**
 * JavaScript for GroupTravelStatusInline to show abort button when adding groups
 * that already have a travel status assigned.
 */
(function($) {
    'use strict';
    
    // Wait for both jQuery and document ready
    $(document).ready(function() {
        console.log('[GroupTravelStatus] Script loaded');
        console.log('[GroupTravelStatus] Groups with status:', window.groupsWithTravelStatus);
        
        // Function to check if a group has an existing travel status and show abort button
        function checkGroupTravelStatus(selectElement) {
            if (!selectElement) {
                console.log('[GroupTravelStatus] No select element provided');
                return;
            }
            
            var $select = $(selectElement);
            var $row = $select.closest('tr');
            var groupId = $select.val();
            
            console.log('[GroupTravelStatus] Checking group:', groupId, 'Row:', $row.length);
            
            // Find or create placeholder in the abort_trip_action column
            var $placeholder = $row.find('.abort-trip-placeholder');
            
            // If no placeholder exists, find the last cell (abort_trip_action column) and add it
            if ($placeholder.length === 0) {
                // Try to find the cell containing "Aktionen" or the last cell
                var $actionCell = $row.find('td').last();
                if ($actionCell.length) {
                    $actionCell.append('<span class="abort-trip-placeholder" style="display: none;"></span>');
                    $placeholder = $actionCell.find('.abort-trip-placeholder');
                    console.log('[GroupTravelStatus] Created placeholder in cell');
                } else {
                    console.log('[GroupTravelStatus] Could not find action cell');
                    return;
                }
            }
            
            if (!groupId) {
                // No group selected - hide placeholder
                $placeholder.hide().html('');
                $row.next('.group-travel-status-warning').remove();
                return;
            }
            
            // Get group status info from global variable (set by template)
            var groupsWithStatus = window.groupsWithTravelStatus || {};
            console.log('[GroupTravelStatus] Looking for group ID:', groupId, 'in:', groupsWithStatus);
            var statusInfo = groupsWithStatus[groupId];
            
            if (statusInfo) {
                console.log('[GroupTravelStatus] Found status info:', statusInfo);
                // Group has existing travel status - show abort button
                var abortUrl = '/admin/api/grouptravelstatus/' + statusInfo.status_id + '/abort_trip/';
                var currentKm = parseFloat(statusInfo.current_km).toLocaleString('de-DE', {
                    minimumFractionDigits: 3,
                    maximumFractionDigits: 3
                }).replace('.', ',');
                
                var confirmMessage = 'Möchten Sie die Reise für diese Gruppe wirklich abbrechen? Die aktuellen Reisekilometer (' + currentKm + ' km) gehen verloren.';
                
                var buttonHtml = '<a href="' + abortUrl + '" class="button" ' +
                    'onclick="return confirm(\'' + confirmMessage.replace(/'/g, "\\'") + '\');">' +
                    'Reise abbrechen</a>';
                
                $placeholder.html(buttonHtml).show();
                console.log('[GroupTravelStatus] Button shown');
                
                // Show warning message
                var warningHtml = '<div class="form-row" style="margin-top: 5px; padding: 10px; background-color: #fff3cd; border: 1px solid #ffc107; border-radius: 4px;">' +
                    '<strong style="color: #856404;">⚠️ Warnung:</strong> ' +
                    '<span style="color: #856404;">Die Gruppe "' + statusInfo.group_name + '" ist bereits der Reise "' + statusInfo.track_name + '" zugeordnet (' + currentKm + ' km). ' +
                    'Bitte brechen Sie die aktuelle Reise ab, bevor Sie die Gruppe einer neuen Reise zuordnen.</span>' +
                    '</div>';
                
                // Remove existing warning if any
                $row.next('.group-travel-status-warning').remove();
                $row.after('<tr class="group-travel-status-warning"><td colspan="3">' + warningHtml + '</td></tr>');
            } else {
                console.log('[GroupTravelStatus] No status info found for group:', groupId);
                // Group has no existing status - hide abort button and warning
                $placeholder.hide().html('');
                $row.next('.group-travel-status-warning').remove();
            }
        }
    
        // Handle group selection change in existing forms
        $(document).on('change', 'select[name$="-group"]', function() {
            console.log('[GroupTravelStatus] Group selection changed');
            var self = this;
            setTimeout(function() {
                checkGroupTravelStatus(self);
            }, 100);
        });
        
        // Handle new inline forms being added
        $(document).on('formset:added', function(event, $row, formsetName) {
            console.log('[GroupTravelStatus] Formset added:', formsetName);
            if (formsetName && formsetName.indexOf('grouptravelstatus') !== -1) {
                setTimeout(function() {
                    var $select = $row.find('select[name$="-group"]');
                    if ($select.length) {
                        checkGroupTravelStatus($select[0]);
                    }
                }, 200);
            }
        });
        
        // Also listen for DOM changes (for cases where formset:added event doesn't fire)
        var observer = new MutationObserver(function(mutations) {
            mutations.forEach(function(mutation) {
                if (mutation.addedNodes.length > 0) {
                    mutation.addedNodes.forEach(function(node) {
                        if (node.nodeType === 1) { // Element node
                            var $select = $(node).find('select[name$="-group"]');
                            if ($select.length === 0 && $(node).is('select[name$="-group"]')) {
                                $select = $(node);
                            }
                            if ($select.length) {
                                setTimeout(function() {
                                    checkGroupTravelStatus($select[0]);
                                }, 100);
                            }
                        }
                    });
                }
            });
        });
        
        // Observe the inline formset container - try multiple selectors
        var formsetContainer = document.querySelector('#grouptravelstatus_set-group') || 
                               document.querySelector('.inline-group') ||
                               document.querySelector('#grouptravelstatus_set-group-group');
        if (formsetContainer) {
            console.log('[GroupTravelStatus] Observing formset container:', formsetContainer);
            observer.observe(formsetContainer, { childList: true, subtree: true });
        } else {
            console.log('[GroupTravelStatus] Formset container not found');
        }
        
        // Check all existing forms on page load
        setTimeout(function() {
            console.log('[GroupTravelStatus] Checking existing forms on page load');
            $('select[name$="-group"]').each(function() {
                checkGroupTravelStatus(this);
            });
        }, 1000);
    });
})(django.jQuery || jQuery);

