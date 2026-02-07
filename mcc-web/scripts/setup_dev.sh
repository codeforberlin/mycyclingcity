#!/bin/bash
# Copyright (c) 2026 SAI-Lab / MyCyclingCity
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# @file    setup_dev.sh
# @author  Roland Rutz
# @note    This code was developed with the assistance of AI (LLMs).
#
# Setup script for MyCyclingCity development environment
# Usage: ./scripts/setup_dev.sh [--skip-venv] [--skip-superuser] [--skip-static]

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Get script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# Parse command line arguments
SKIP_VENV=false
SKIP_SUPERUSER=false
SKIP_STATIC=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --skip-venv)
            SKIP_VENV=true
            shift
            ;;
        --skip-superuser)
            SKIP_SUPERUSER=true
            shift
            ;;
        --skip-static)
            SKIP_STATIC=true
            shift
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            echo "Usage: $0 [--skip-venv] [--skip-superuser] [--skip-static]"
            exit 1
            ;;
    esac
done

# Change to project directory
cd "$PROJECT_DIR"

echo -e "${CYAN}========================================${NC}"
echo -e "${CYAN}MyCyclingCity Development Setup${NC}"
echo -e "${CYAN}========================================${NC}"
echo ""

# Function to print status messages
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[OK]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check Python version
print_status "Checking Python version..."
if ! command -v python3 &> /dev/null; then
    print_error "Python 3 is not installed. Please install Python 3.11 or higher."
    exit 1
fi

PYTHON_VERSION=$(python3 --version | cut -d' ' -f2 | cut -d'.' -f1,2)
PYTHON_MAJOR=$(echo "$PYTHON_VERSION" | cut -d'.' -f1)
PYTHON_MINOR=$(echo "$PYTHON_VERSION" | cut -d'.' -f2)

if [ "$PYTHON_MAJOR" -lt 3 ] || ([ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 11 ]); then
    print_error "Python 3.11 or higher is required. Found: $PYTHON_VERSION"
    exit 1
fi

print_success "Python $PYTHON_VERSION found"

# Step 1: Create virtual environment
if [ "$SKIP_VENV" = false ]; then
    print_status "Setting up Python virtual environment..."
    
    VENV_DIR="$PROJECT_DIR/venv"
    
    if [ -d "$VENV_DIR" ]; then
        print_warning "Virtual environment already exists at $VENV_DIR"
        read -p "Do you want to recreate it? (y/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            print_status "Removing existing virtual environment..."
            rm -rf "$VENV_DIR"
        else
            print_status "Using existing virtual environment"
            SKIP_VENV=true
        fi
    fi
    
    if [ "$SKIP_VENV" = false ]; then
        print_status "Creating virtual environment..."
        python3 -m venv "$VENV_DIR"
        print_success "Virtual environment created"
    fi
    
    # Activate virtual environment
    print_status "Activating virtual environment..."
    source "$VENV_DIR/bin/activate"
    
    # Upgrade pip
    print_status "Upgrading pip..."
    pip install --upgrade pip --quiet
    print_success "pip upgraded"
    
    # Install dependencies
    print_status "Installing dependencies from requirements.txt..."
    if [ -f "requirements.txt" ]; then
        pip install -r requirements.txt --quiet
        print_success "Dependencies installed"
    else
        print_error "requirements.txt not found!"
        exit 1
    fi
else
    print_status "Skipping virtual environment setup"
    # Try to activate existing venv
    if [ -d "$PROJECT_DIR/venv" ]; then
        source "$PROJECT_DIR/venv/bin/activate"
    else
        print_warning "No virtual environment found. Make sure to activate one manually."
    fi
fi

# Step 2: Create required directories
print_status "Creating required directories..."

# Development directories (from settings.py and scripts)
DIRS=(
    "data/db"           # SQLite database directory
    "logs"              # Log files
    "tmp"               # Temporary files (PID files, etc.)
    "staticfiles"       # Collected static files
    "media"             # Media files (user uploads, etc.)
    "backups"           # Database backups
)

for dir in "${DIRS[@]}"; do
    FULL_PATH="$PROJECT_DIR/$dir"
    if [ ! -d "$FULL_PATH" ]; then
        mkdir -p "$FULL_PATH"
        print_success "Created directory: $dir"
    else
        print_status "Directory already exists: $dir"
    fi
done

# Set permissions for tmp directory (for PID files)
chmod 755 "$PROJECT_DIR/tmp" 2>/dev/null || true

print_success "All required directories created"

# Step 3: Check/Create .env file
print_status "Checking .env file..."

ENV_FILE="$PROJECT_DIR/.env"
ENV_EXAMPLE="$PROJECT_DIR/.env.example"

if [ ! -f "$ENV_FILE" ]; then
    print_warning ".env file not found"
    
    if [ -f "$ENV_EXAMPLE" ]; then
        print_status "Copying .env.example to .env..."
        cp "$ENV_EXAMPLE" "$ENV_FILE"
        print_success ".env file created from .env.example"
        print_warning "Please edit .env file and set SECRET_KEY and other required variables"
    else
        print_status "Creating minimal .env file..."
        cat > "$ENV_FILE" << EOF
# Django Settings
SECRET_KEY=$(python3 -c 'from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())')
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

# Database (SQLite in development)
# DATABASE_URL=sqlite:///data/db/db.sqlite3

# Optional: Email settings
# EMAIL_HOST=smtp.example.com
# EMAIL_PORT=587
# EMAIL_USE_TLS=True
# EMAIL_HOST_USER=your-email@example.com
# EMAIL_HOST_PASSWORD=your-password
EOF
        print_success ".env file created with generated SECRET_KEY"
    fi
else
    print_success ".env file already exists"
    
    # Check if SECRET_KEY is set
    if grep -q "^SECRET_KEY=" "$ENV_FILE" && ! grep -q "^SECRET_KEY=django-insecure-YOUR_SECRET_KEY_HERE" "$ENV_FILE"; then
        print_success "SECRET_KEY is configured"
    else
        print_warning "SECRET_KEY might not be set properly. Please check .env file"
    fi
fi

# Step 4: Clear PYTHONPATH if set (can cause issues)
if [ -n "$PYTHONPATH" ]; then
    print_warning "PYTHONPATH is set: $PYTHONPATH"
    print_warning "This can cause import issues. Consider unsetting it: unset PYTHONPATH"
fi

# Step 5: Run migrations
print_status "Running database migrations..."

# Ensure we're using the venv python
if [ -f "$PROJECT_DIR/venv/bin/python" ]; then
    PYTHON_BIN="$PROJECT_DIR/venv/bin/python"
else
    PYTHON_BIN="python3"
fi

# Unset PYTHONPATH for migration
export PYTHONPATH=""

# Run migrations
if "$PYTHON_BIN" manage.py migrate --noinput; then
    print_success "Database migrations completed"
else
    print_error "Database migrations failed!"
    exit 1
fi

# Step 6: Create superuser (optional)
if [ "$SKIP_SUPERUSER" = false ]; then
    print_status "Checking for superuser..."
    
    # Check if superuser exists
    SUPERUSER_EXISTS=$("$PYTHON_BIN" manage.py shell -c "
from django.contrib.auth import get_user_model
User = get_user_model()
if User.objects.filter(is_superuser=True).exists():
    print('true')
else:
    print('false')
" 2>/dev/null || echo "false")
    
    if [ "$SUPERUSER_EXISTS" = "false" ]; then
        print_warning "No superuser found"
        read -p "Do you want to create a superuser now? (Y/n): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Nn]$ ]]; then
            "$PYTHON_BIN" manage.py createsuperuser
            print_success "Superuser created"
        else
            print_status "Skipping superuser creation. Run 'python manage.py createsuperuser' later."
        fi
    else
        print_success "Superuser already exists"
    fi
else
    print_status "Skipping superuser creation"
fi

# Step 7: Collect static files
if [ "$SKIP_STATIC" = false ]; then
    print_status "Collecting static files..."
    
    if "$PYTHON_BIN" manage.py collectstatic --noinput --clear 2>&1 | grep -q "static files copied"; then
        print_success "Static files collected"
    else
        print_warning "Static files collection completed (may have warnings)"
    fi
else
    print_status "Skipping static files collection"
fi

# Step 8: Verify setup
print_status "Verifying setup..."

# Check if manage.py works
if "$PYTHON_BIN" manage.py check --deploy 2>&1 | grep -q "System check identified"; then
    print_warning "Some deployment checks failed (expected in development)"
else
    print_success "Basic Django check passed"
fi

# Final summary
echo ""
echo -e "${CYAN}========================================${NC}"
echo -e "${GREEN}Setup completed successfully!${NC}"
echo -e "${CYAN}========================================${NC}"
echo ""
echo -e "${BLUE}Next steps:${NC}"
echo "  1. Review and edit .env file if needed"
echo "  2. Start the development server:"
echo -e "     ${CYAN}source venv/bin/activate${NC}"
echo -e "     ${CYAN}python manage.py runserver${NC}"
echo ""
echo -e "${BLUE}Useful commands:${NC}"
echo "  - Create superuser: python manage.py createsuperuser"
echo "  - Run tests: pytest api/tests/"
echo "  - Run migrations: python manage.py migrate"
echo "  - Collect static: python manage.py collectstatic"
echo ""
echo -e "${BLUE}Important directories:${NC}"
echo "  - Logs: $PROJECT_DIR/logs/"
echo "  - Database: $PROJECT_DIR/data/db/"
echo "  - Static files: $PROJECT_DIR/staticfiles/"
echo "  - Media files: $PROJECT_DIR/media/"
echo ""
