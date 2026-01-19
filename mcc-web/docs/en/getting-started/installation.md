# Installation Guide

This guide explains how to set up the MyCyclingCity development environment.

## Prerequisites

- Python 3.11 or higher
- pip (Python package manager)
- Git
- Virtual environment (recommended)

## Step 1: Clone the Repository

```bash
git clone https://github.com/codeforberlin/mycyclingcity.git
cd mycyclingcity
```

## Step 2: Set Up Python Virtual Environment

### Option A: Project-local Virtual Environment (Recommended)

```bash
cd mcc-web
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### Option B: External Virtual Environment

For development on different systems with different Python installations (e.g., NAS server):

```bash
# Create virtual environment in home directory
python3 -m venv ~/venv_mcc
source ~/venv_mcc/bin/activate
```

## Step 3: Install Dependencies

```bash
cd mcc-web
pip install --upgrade pip
pip install -r requirements.txt
```

### Required Packages

- Django==5.2.9
- requests==2.32.5
- gunicorn==23.0.0
- gpxpy==1.6.2
- pillow==12.0.0
- python-decouple==3.8
- python-dotenv==1.0.0
- pytest==8.0.0
- pytest-django==4.8.0
- factory-boy==3.3.0
- qrcode[pil]==7.4.2

## Step 4: Configure Environment Variables

Create a `.env` file in the `mcc-web/` directory:

```bash
cp .env.example .env  # If example exists
# Or create manually
```

Minimum required variables:

```env
SECRET_KEY=your-secret-key-here
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
```

## Step 5: Run Database Migrations

```bash
python manage.py migrate
```

## Step 6: Create Superuser (Optional)

```bash
python manage.py createsuperuser
```

## Step 7: Collect Static Files

```bash
python manage.py collectstatic
```

## Step 8: Run Development Server

```bash
python manage.py runserver
```

Access the application:
- Admin: http://127.0.0.1:8000/admin
- Game: http://127.0.0.1:8000/de/game/
- Map: http://127.0.0.1:8000/de/map/

## Verification

To verify the installation:

1. Check that the server starts without errors
2. Access the admin interface at `/admin`
3. Run tests: `pytest api/tests/`

## Troubleshooting

### Import Errors

- Ensure virtual environment is activated
- Verify all dependencies are installed: `pip list`
- Check Python version: `python --version` (should be 3.11+)

### Database Errors

- Ensure SQLite is available (included with Python)
- Check file permissions for `db.sqlite3`
- Run migrations: `python manage.py migrate`

### Static Files Not Loading

- Run `python manage.py collectstatic`
- Check `STATIC_ROOT` in `config/settings.py`
- Verify `DEBUG=True` in development

## Next Steps

- [Configuration Guide](configuration.md) - Configure the application
- [Admin GUI Manual](../admin/index.md) - Learn to use the admin interface
- [API Reference](../api/index.md) - Explore the API
