# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    admin_views.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

#
"""
Admin helper views for bulk creation of schools, classes, and players.
"""

from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.views.decorators.http import require_http_methods
from django.db import transaction
from django.http import JsonResponse
from django.utils.translation import gettext_lazy as _
from api.models import Group, Cyclist, GroupType
import logging
import re
import re

logger = logging.getLogger(__name__)


@staff_member_required
@require_http_methods(["GET", "POST"])
def bulk_create_school(request):
    """
    Admin tool for bulk creation of schools, classes, and players.
    
    GET: Display the form
    POST: Process the form and create groups/players
    """
    if request.method == 'GET':
        group_types = GroupType.objects.filter(is_active=True).order_by('name')
        return render(request, 'admin/api/bulk_create_school.html', {
            'title': _('Massenerstellung: Schule, Klassen und Radler'),
            'group_types': group_types,
        })
    
    # POST: Process form data
    try:
        with transaction.atomic():
            # Get form data
            school_name = request.POST.get('school_name', '').strip()
            school_short_name = request.POST.get('school_short_name', '').strip()
            school_group_type_id = request.POST.get('school_group_type')
            
            if not school_name:
                messages.error(request, _('Schulname ist erforderlich.'))
                group_types = GroupType.objects.filter(is_active=True).order_by('name')
                return render(request, 'admin/api/bulk_create_school.html', {
                    'title': _('Massenerstellung: Schule, Klassen und Radler'),
                    'group_types': group_types,
                })
            
            # Get GroupType object
            try:
                school_group_type = GroupType.objects.get(pk=school_group_type_id, is_active=True)
            except (GroupType.DoesNotExist, ValueError, TypeError):
                # Fallback to default 'Schule' type
                school_group_type, _ = GroupType.objects.get_or_create(name='Schule', defaults={'is_active': True})
            
            # Create parent school group
            # Check if school already exists
            try:
                school_group = Group.objects.get(group_type=school_group_type, name=school_name)
                created = False
                # Update short_name if provided and not set
                if school_short_name and not school_group.short_name:
                    school_group.short_name = school_short_name
                    school_group.save()
            except Group.DoesNotExist:
                school_group = Group.objects.create(
                    group_type=school_group_type,
                    name=school_name,
                    short_name=school_short_name if school_short_name else None,
                    is_visible=request.POST.get('school_is_visible', 'on') == 'on',
                )
                created = True
            
            # Get 'Klasse' GroupType for classes
            try:
                class_group_type = GroupType.objects.get(name='Klasse', is_active=True)
            except GroupType.DoesNotExist:
                class_group_type, _ = GroupType.objects.get_or_create(name='Klasse', defaults={'is_active': True})
            
            if not created:
                messages.warning(request, _('Schule "{}" existiert bereits. Klassen werden hinzugefügt.').format(school_name))
            
            # Process classes
            created_classes = []
            created_players = []
            
            # Get class data from form
            class_numbers = request.POST.getlist('class_number[]')
            class_letters = request.POST.getlist('class_letter[]')
            class_short_names = request.POST.getlist('class_short_name[]')
            class_player_counts = request.POST.getlist('class_player_count[]')
            class_is_visible = request.POST.getlist('class_is_visible[]')
            
            for i, class_number in enumerate(class_numbers):
                if not class_number or not class_letters[i]:
                    continue
                
                class_letter = class_letters[i]
                class_short_name = class_short_names[i] if i < len(class_short_names) else ''
                player_count = int(class_player_counts[i]) if i < len(class_player_counts) and class_player_counts[i] else 0
                is_visible = i < len(class_is_visible) and class_is_visible[i] == 'on'
                
                # Generate unique class name: school-class (e.g. "SchuleC-1a")
                # Use short_name if available, otherwise use normalized school name
                school_identifier_for_class = (school_short_name or school_name).strip()
                # Remove special characters that might cause issues
                school_identifier_for_class = re.sub(r'[^\w\s-]', '', school_identifier_for_class)
                
                class_base_name = f"{class_number}{class_letter}"
                # Unique class name: school-class
                class_name = f"{school_identifier_for_class}-{class_base_name}"
                
                # Short name for display (e.g. "1a" or "1a-SchuleC")
                if not class_short_name:
                    if school_short_name:
                        class_short_name = f"{class_base_name}-{school_short_name}"
                    else:
                        class_short_name = class_base_name
                
                # Create class group - check if it already exists with this parent
                try:
                    class_group = Group.objects.get(
                        group_type=class_group_type,
                        name=class_name,
                        parent=school_group
                    )
                    class_created = False
                except Group.DoesNotExist:
                    # Check if class exists with different parent (would violate unique constraint)
                    existing_class = Group.objects.filter(
                        group_type=class_group_type,
                        name=class_name
                    ).first()
                    
                    if existing_class:
                        # Class exists but with different parent - skip with warning
                        logger.warning(
                            f"Class '{class_name}' already exists with parent '{existing_class.parent}' "
                            f"(not '{school_group.name}'). Skipping."
                        )
                        continue
                    
                    class_group = Group.objects.create(
                        group_type=class_group_type,
                        name=class_name,
                        parent=school_group,
                        short_name=class_short_name,
                        is_visible=is_visible,
                    )
                    class_created = True
                
                if class_created:
                    created_classes.append(class_group)
                
                # Generate unique school identifier for player ID tags
                # Use short_name if available, otherwise use normalized school name
                school_identifier = (school_short_name or school_name).lower()
                # Remove spaces and special characters, keep only alphanumeric and hyphens
                school_identifier = re.sub(r'[^a-z0-9-]', '', school_identifier.replace(' ', '-'))
                
                # Create players for this class (even if class already existed)
                for player_num in range(1, player_count + 1):
                    # User ID is just a symbolic name for display (e.g. "1a/1")
                    # It doesn't need to be unique - the id_tag (RFID-UID) is the unique identifier
                    player_user_id = f"{class_base_name}/{player_num}"
                    # Unique ID tag: school-class-number (e.g. "schulec-1a-01")
                    # This will be replaced with the actual RFID-UID when the tag is assigned
                    player_id_tag = f"{school_identifier}-{class_base_name.lower()}-{player_num:02d}"
                    
                    # Check if player already exists
                    try:
                        cyclist = Cyclist.objects.get(id_tag=player_id_tag)
                        cyclist_created = False
                    except Cyclist.DoesNotExist:
                        cyclist = Cyclist.objects.create(
                            id_tag=player_id_tag,
                            user_id=player_user_id,
                            is_visible=request.POST.get('cyclist_is_visible', 'on') == 'on',
                            is_km_collection_enabled=request.POST.get('cyclist_is_km_enabled', 'on') == 'on',
                        )
                        cyclist_created = True
                    
                    if cyclist_created:
                        # Add cyclist to class group
                        cyclist.groups.add(class_group)
                        created_players.append(cyclist)
                    elif class_group not in cyclist.groups.all():
                        # Cyclist exists but not in this class - add them
                        cyclist.groups.add(class_group)
            
            # Success message
            messages.success(
                request,
                _('Erfolgreich erstellt: 1 Schule, {} Klassen, {} Spieler').format(
                    len(created_classes),
                    len(created_players)
                )
            )
            
            logger.info(
                f"[bulk_create_school] Created school '{school_name}' with {len(created_classes)} classes "
                f"and {len(created_players)} players by user {request.user.username}"
            )
            
            return redirect('admin:api_group_changelist')
            
    except Exception as e:
        logger.error(f"[bulk_create_school] Error: {str(e)}", exc_info=True)
        messages.error(request, _('Fehler beim Erstellen: {}').format(str(e)))
        return render(request, 'admin/api/bulk_create_school.html', {
            'title': _('Massenerstellung: Schule, Klassen und Spieler'),
        })


@staff_member_required
@require_http_methods(["POST"])
def bulk_create_school_preview(request):
    """
    HTMX endpoint to preview what will be created without actually creating it.
    """
    try:
        school_name = request.POST.get('school_name', '').strip()
        school_short_name = request.POST.get('school_short_name', '').strip()
        class_numbers = request.POST.getlist('class_number[]')
        class_letters = request.POST.getlist('class_letter[]')
        class_short_names = request.POST.getlist('class_short_name[]')
        class_player_counts = request.POST.getlist('class_player_count[]')
        
        preview_data = {
            'school': {
                'name': school_name,
                'short_name': school_short_name or school_name,
            },
            'classes': []
        }
        
        for i, class_number in enumerate(class_numbers):
            if not class_number or i >= len(class_letters) or not class_letters[i]:
                continue
            
            class_letter = class_letters[i]
            class_short_name = class_short_names[i] if i < len(class_short_names) else ''
            player_count = int(class_player_counts[i]) if i < len(class_player_counts) and class_player_counts[i] else 0
            
            # Generate unique class name: school-class
            school_identifier_for_class = (school_short_name or school_name).strip()
            school_identifier_for_class = re.sub(r'[^\w\s-]', '', school_identifier_for_class)
            
            class_base_name = f"{class_number}{class_letter}"
            class_name = f"{school_identifier_for_class}-{class_base_name}"
            
            # Short name for display
            if not class_short_name:
                if school_short_name:
                    class_short_name = f"{class_base_name}-{school_short_name}"
                else:
                    class_short_name = class_base_name
            
            # Generate unique school identifier for player ID tags
            school_identifier = (school_short_name or school_name).lower()
            school_identifier = re.sub(r'[^a-z0-9-]', '', school_identifier.replace(' ', '-'))
            
            players = []
            for player_num in range(1, player_count + 1):
                # User ID is just a symbolic name for display (e.g. "1a/1")
                # The id_tag is the unique identifier (will be replaced with actual RFID-UID later)
                players.append({
                    'user_id': f"{class_base_name}/{player_num}",
                    'id_tag': f"{school_identifier}-{class_base_name.lower()}-{player_num:02d}",
                })
            
            preview_data['classes'].append({
                'name': class_name,
                'base_name': class_base_name,
                'short_name': class_short_name,
                'player_count': player_count,
                'players': players,
            })
        
        # Calculate total cyclists
        total_cyclists = sum(class_data['cyclist_count'] for class_data in preview_data['classes'])
        preview_data['total_cyclists'] = total_cyclists
        
        # Return HTML fragment directly (for HTMX)
        return render(request, 'admin/api/bulk_create_school_preview.html', {
            'preview': preview_data,
        })
        
    except Exception as e:
        logger.error(f"[bulk_create_school_preview] Error: {str(e)}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=400)

