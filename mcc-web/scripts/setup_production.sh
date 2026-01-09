#!/bin/bash
# Production setup script for MCC-Web systemd service
#
# This script automates the installation and configuration of the MCC-Web
# systemd service on the production server.
#
# Usage:
#   sudo ./scripts/setup_production.sh

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Production paths
PROD_BASE="/data/games/mcc/mycyclingcity"
PROD_WEB_DIR="${PROD_BASE}/mcc-web"
SERVICE_FILE="${PROD_WEB_DIR}/scripts/mcc-web.service"
SYSTEMD_TARGET="/etc/systemd/system/mcc-web.service"
ENV_FILE="${PROD_WEB_DIR}/.env"

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}Error: This script must be run as root (use sudo)${NC}"
    exit 1
fi

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}MCC-Web Production Setup${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Step 1: Check if production directory exists
echo -e "${BLUE}[1/5]${NC} Checking production directory..."
if [ ! -d "$PROD_WEB_DIR" ]; then
    echo -e "${RED}Error: Production directory not found: $PROD_WEB_DIR${NC}"
    echo -e "${YELLOW}Please ensure the application is deployed to the production path.${NC}"
    exit 1
fi
echo -e "${GREEN}✓${NC} Production directory exists: $PROD_WEB_DIR"

# Step 2: Check if service file exists
echo -e "${BLUE}[2/5]${NC} Checking service file..."
if [ ! -f "$SERVICE_FILE" ]; then
    echo -e "${RED}Error: Service file not found: $SERVICE_FILE${NC}"
    exit 1
fi
echo -e "${GREEN}✓${NC} Service file found: $SERVICE_FILE"

# Step 3: Check if .env file exists
echo -e "${BLUE}[3/5]${NC} Checking .env file..."
if [ ! -f "$ENV_FILE" ]; then
    echo -e "${YELLOW}⚠${NC} Warning: .env file not found: $ENV_FILE"
    echo -e "${YELLOW}   The service will start, but Django may use default values.${NC}"
    echo -e "${YELLOW}   It is recommended to create a .env file before starting the service.${NC}"
    read -p "Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo -e "${RED}Setup cancelled.${NC}"
        exit 1
    fi
else
    echo -e "${GREEN}✓${NC} .env file found: $ENV_FILE"
fi

# Step 4: Copy service file to systemd
echo -e "${BLUE}[4/5]${NC} Installing systemd service..."
if [ -f "$SYSTEMD_TARGET" ]; then
    echo -e "${YELLOW}⚠${NC} Service file already exists at $SYSTEMD_TARGET"
    read -p "Overwrite? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo -e "${YELLOW}Keeping existing service file.${NC}"
    else
        cp "$SERVICE_FILE" "$SYSTEMD_TARGET"
        echo -e "${GREEN}✓${NC} Service file installed"
    fi
else
    cp "$SERVICE_FILE" "$SYSTEMD_TARGET"
    echo -e "${GREEN}✓${NC} Service file installed"
fi

# Step 5: Reload systemd and enable service
echo -e "${BLUE}[5/5]${NC} Configuring systemd..."
systemctl daemon-reload
echo -e "${GREEN}✓${NC} Systemd daemon reloaded"

systemctl enable mcc-web
echo -e "${GREEN}✓${NC} Service enabled (will start on boot)"

# Check if service is already running
if systemctl is-active --quiet mcc-web; then
    echo -e "${YELLOW}⚠${NC} Service is already running. Restarting..."
    systemctl restart mcc-web
    echo -e "${GREEN}✓${NC} Service restarted"
else
    echo -e "${BLUE}ℹ${NC} Service is not running. Starting..."
    systemctl start mcc-web
    echo -e "${GREEN}✓${NC} Service started"
fi

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Setup completed successfully!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "Service status:"
systemctl status mcc-web --no-pager -l || true
echo ""
echo "Useful commands:"
echo "  sudo systemctl status mcc-web    # Check service status"
echo "  sudo systemctl restart mcc-web    # Restart service"
echo "  sudo systemctl stop mcc-web       # Stop service"
echo "  sudo systemctl start mcc-web      # Start service"
echo "  sudo journalctl -u mcc-web -f    # View logs (follow mode)"
echo ""

