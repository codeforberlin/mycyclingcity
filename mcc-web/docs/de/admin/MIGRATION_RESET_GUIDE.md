# Migration Reset Guide

This guide explains how to reset or consolidate database migrations for a clean production installation.

## Overview

After completing the first development phase, it may be useful to consolidate migrations to:
- Have a clean setup for production
- Simplify the migration history
- Avoid potential migration problems

## Two Approaches

### Option 1: Squashing Migrations (Recommended)

**Advantages:**
- Preserves migration history
- Backward compatible with existing databases
- Django-recommended approach

**Disadvantages:**
- Can be complex with many migrations
- Creates additional squash files

**When to use:**
- If a production database already exists
- If you want to keep the history

### Option 2: Complete Migration Regeneration

**Advantages:**
- Clean, simple migration structure
- Only one initial migration per app
- Easier to understand and maintain

**Disadvantages:**
- Loses migration history
- Only possible if no production database exists
- Data migrations must be manually re-added

**When to use:**
- Before the first production deployment
- If the development database can be reset
- For a completely clean setup

## Using the Reset Script

### Squashing Migrations

```bash
# Squash all apps
python utils/reset_migrations.py --mode squash

# Squash specific apps
python utils/reset_migrations.py --mode squash --apps api kiosk
```

### Complete Migration Regeneration

```bash
# Full reset (deletes migrations and database)
python utils/reset_migrations.py --mode reset

# Reset without deleting database
python utils/reset_migrations.py --mode reset --no-delete-db

# Reset without creating new database
python utils/reset_migrations.py --mode reset --no-create-db

# Reset specific apps
python utils/reset_migrations.py --mode reset --apps api
```

## Important Steps for Option 2 (Complete Reset)

### 1. Preparation

```bash
# 1. Ensure all model changes are committed
git status

# 2. Backup current migrations (done automatically)
# Backups are stored in migration_backups/

# 3. Backup database (if important)
cp data/db.sqlite3 data/db.sqlite3.backup
```

### 2. Perform Reset

```bash
# Reset with automatic backup
python utils/reset_migrations.py --mode reset
```

The script:
- Creates backup of migrations
- Deletes all migrations (except `__init__.py`)
- Deletes the database
- Generates new initial migrations
- Creates new database

### 3. Re-add Data Migrations

After the reset, data migrations must be manually re-added.

**Example: GroupType Population**

The migration `0005_populate_group_types.py` creates default GroupType entries. These must be integrated into the new initial migration:

1. Open the new initial migration (e.g., `api/migrations/0001_initial.py`)
2. Add the data migration at the end of the `operations` list:

```python
# In api/migrations/0001_initial.py

def populate_group_types(apps, schema_editor):
    """Create default GroupType entries: 'Schule' and 'Klasse'."""
    GroupType = apps.get_model('api', 'GroupType')
    
    GroupType.objects.get_or_create(
        name='Schule',
        defaults={
            'description': 'Übergeordnete Gruppe für Schulen',
            'is_active': True
        }
    )
    
    GroupType.objects.get_or_create(
        name='Klasse',
        defaults={
            'description': 'Untergeordnete Gruppe für Klassen',
            'is_active': True
        }
    )


class Migration(migrations.Migration):
    initial = True
    dependencies = [...]
    
    operations = [
        # ... all CreateModel, AddField, etc. ...
        
        # Data migration at the end
        migrations.RunPython(populate_group_types),
    ]
```

**Alternative:** Create a separate data migration after the initial migration:

```bash
python manage.py makemigrations api --empty --name populate_group_types
```

Then add the code to the new migration.

### 4. Testing

```bash
# 1. Delete and recreate database
rm data/db.sqlite3*
python manage.py migrate

# 2. Check if data migration works
python manage.py shell
>>> from api.models import GroupType
>>> GroupType.objects.all()
# Should show 'Schule' and 'Klasse'

# 3. Run tests
python manage.py test
```

### 5. Test Deployment Scripts

```bash
# Test the deployment script with the new database
python utils/deploy_production.py
```

## Current Data Migrations in Project

### api/migrations/0005_populate_group_types.py

This migration creates default GroupType entries:
- `Schule` (Parent group)
- `Klasse` (Child group)

**Important:** This must be re-added after a reset!

## Production Deployment Checklist

- [ ] Migrations reset/consolidated
- [ ] Data migrations re-added
- [ ] New migrations tested (clean database)
- [ ] Deployment script tested
- [ ] Backup strategy defined
- [ ] Rollback plan created

## Rollback in Case of Problems

If problems occur after the reset:

1. **Restore migrations:**
   ```bash
   # From backup directory
   cp migration_backups/api/*.py api/migrations/
   ```

2. **Restore database:**
   ```bash
   cp data/db.sqlite3.backup data/db.sqlite3
   ```

3. **Use Git (if committed):**
   ```bash
   git checkout api/migrations/
   ```

## Recommendation for Your Project

Based on the current structure (15 migrations for api, multiple initial migrations):

**Recommended approach: Option 2 (Complete Reset)**

**Reasons:**
1. No production database exists yet
2. Two "initial" migrations (0001 and 0002) indicate development phase
3. Clean setup for production is desirable
4. Development database can be reset

**Procedure:**
1. Perform reset: `python utils/reset_migrations.py --mode reset`
2. Re-add data migration (GroupType)
3. Test with clean database
4. Test deployment script
5. Perform production deployment

## Additional Resources

- Django Migrations: https://docs.djangoproject.com/en/stable/topics/migrations/
- Squash Migrations: https://docs.djangoproject.com/en/stable/topics/migrations/#squashing-migrations
- Data Migrations: https://docs.djangoproject.com/en/stable/topics/migrations/#data-migrations
