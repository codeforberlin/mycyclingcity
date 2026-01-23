# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    fix_sessions_table.py
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).

#
"""
Management command to fix missing django_session table.

This command checks if the django_session table exists and creates it if missing.
"""

from django.core.management.base import BaseCommand
from django.db import connection, models
from django.core.management import call_command
from django.contrib.sessions.models import Session


class Command(BaseCommand):
    help = 'Fix missing django_session table by creating it directly'

    def handle(self, *args, **options):
        self.stdout.write("Checking django_session table...")
        
        # Check if table exists
        table_exists = False
        with connection.cursor() as cursor:
            if connection.vendor == 'sqlite':
                cursor.execute("""
                    SELECT name FROM sqlite_master 
                    WHERE type='table' AND name='django_session'
                """)
                table_exists = cursor.fetchone() is not None
            elif connection.vendor == 'postgresql':
                cursor.execute("""
                    SELECT tablename FROM pg_tables 
                    WHERE schemaname = 'public' AND tablename = 'django_session'
                """)
                table_exists = cursor.fetchone() is not None
            else:
                # Try to query the table
                try:
                    cursor.execute("SELECT 1 FROM django_session LIMIT 1")
                    table_exists = True
                except Exception:
                    table_exists = False
        
        if table_exists:
            self.stdout.write(
                self.style.SUCCESS("✓ django_session table exists")
            )
            return
        
        self.stdout.write(
            self.style.WARNING("✗ django_session table does NOT exist")
        )
        self.stdout.write("Creating django_session table...")
        
        try:
            # Create the table directly using SQL
            with connection.cursor() as cursor:
                if connection.vendor == 'sqlite':
                    # SQLite CREATE TABLE statement
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS django_session (
                            session_key VARCHAR(40) PRIMARY KEY,
                            session_data TEXT NOT NULL,
                            expire_date DATETIME NOT NULL
                        )
                    """)
                    # Create index
                    cursor.execute("""
                        CREATE INDEX IF NOT EXISTS django_session_expire_date_a5c62663 
                        ON django_session(expire_date)
                    """)
                elif connection.vendor == 'postgresql':
                    # PostgreSQL CREATE TABLE statement
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS django_session (
                            session_key VARCHAR(40) PRIMARY KEY,
                            session_data TEXT NOT NULL,
                            expire_date TIMESTAMP WITH TIME ZONE NOT NULL
                        )
                    """)
                    # Create index
                    cursor.execute("""
                        CREATE INDEX IF NOT EXISTS django_session_expire_date_a5c62663 
                        ON django_session(expire_date)
                    """)
                else:
                    # For other databases, use Django's schema editor
                    with connection.schema_editor() as schema_editor:
                        # Create a temporary model to generate the table
                        class TempSession(models.Model):
                            session_key = models.CharField(max_length=40, primary_key=True)
                            session_data = models.TextField()
                            expire_date = models.DateTimeField(db_index=True)
                            
                            class Meta:
                                db_table = 'django_session'
                                managed = False
                        
                        schema_editor.create_model(TempSession)
            
            self.stdout.write(
                self.style.SUCCESS("✓ django_session table created successfully")
            )
            
            # Verify the table was created
            with connection.cursor() as cursor:
                if connection.vendor == 'sqlite':
                    cursor.execute("""
                        SELECT name FROM sqlite_master 
                        WHERE type='table' AND name='django_session'
                    """)
                elif connection.vendor == 'postgresql':
                    cursor.execute("""
                        SELECT tablename FROM pg_tables 
                        WHERE schemaname = 'public' AND tablename = 'django_session'
                    """)
                else:
                    cursor.execute("SELECT 1 FROM django_session LIMIT 1")
                
                if cursor.fetchone():
                    self.stdout.write(
                        self.style.SUCCESS("✓ Table verified and ready to use")
                    )
                else:
                    self.stdout.write(
                        self.style.ERROR("✗ Table creation may have failed")
                    )
                    
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"✗ Error creating table: {e}")
            )
            self.stdout.write(
                self.style.WARNING(
                    "\nTrying alternative method: Running migrations with --fake-initial..."
                )
            )
            try:
                # Try to unapply and reapply the migration
                call_command('migrate', 'sessions', '0001', '--fake')
                call_command('migrate', 'sessions', verbosity=1)
                self.stdout.write(
                    self.style.SUCCESS("✓ Sessions migrations completed")
                )
            except Exception as e2:
                self.stdout.write(
                    self.style.ERROR(f"✗ Alternative method also failed: {e2}")
                )
                self.stdout.write(
                    self.style.WARNING(
                        "\nManual fix required. Try:\n"
                        "1. python manage.py migrate sessions --fake-initial\n"
                        "2. Or manually create the table using SQL"
                    )
                )
