# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    fix_groups.py
# @author  Roland Rutz

#
import os
import sys
import django
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from api.models import Group, Cyclist

def fix_hierarchy():
    print("--- Starte Bereinigung der Gruppenhierarchie ---")

    # Step 1: Assign classes uniquely to schools
    # We search for groups that have a name like '1a', '2b' etc.
    # and ensure they have a parent.
    klassen = Group.objects.filter(group_type='Klasse')  # If group_type is named like this
    
    for klasse in klassen:
        if not klasse.parent:
            print(f"WARNUNG: Klasse '{klasse.name}' (ID: {klasse.id}) hat keine Schule als Parent!")
        else:
            print(f"OK: Klasse '{klasse.name}' gehört zu '{klasse.parent.name}'.")

    # Step 2: Clean up cyclist assignments
    # A cyclist should be in '1a'. The '1a' knows which school it belongs to.
    # The cyclist no longer needs to be directly in the 'School A' group.
    cyclists = Cyclist.objects.all()
    for cyclist in cyclists:
        groups = cyclist.groups.all()
        schools = [g for g in groups if g.group_type == 'Schule']
        classes = [g for g in groups if g.group_type == 'Klasse']

        if schools and classes:
            # Wenn der Radler in beiden ist, entfernen wir die direkte Schul-Zuordnung
            for school in schools:
                cyclist.groups.remove(school)
            print(f"Bereinigt: Radler {cyclist.user_id} wurde aus direkter Schulgruppe entfernt.")

    print("--- Bereinigung abgeschlossen ---")

if __name__ == "__main__":
    fix_hierarchy()

