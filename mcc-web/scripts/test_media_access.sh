#!/bin/bash
# Test script to verify media file access via Apache
# Usage: ./test_media_access.sh [filename]

set -e

MEDIA_DIR="/data/var/mcc/media/group_logos"
TEST_FILE="${1:-MCC-Button-v2-300x300.png}"
FULL_PATH="${MEDIA_DIR}/${TEST_FILE}"

echo "=== Media File Access Test ==="
echo ""

# Check if file exists
echo "1. Checking if file exists..."
if [ -f "$FULL_PATH" ]; then
    echo "   ✓ File exists: $FULL_PATH"
    ls -lh "$FULL_PATH"
else
    echo "   ✗ File NOT found: $FULL_PATH"
    exit 1
fi

echo ""

# Check permissions
echo "2. Checking permissions..."
FILE_PERMS=$(stat -c "%a %U:%G" "$FULL_PATH")
DIR_PERMS=$(stat -c "%a %U:%G" "$MEDIA_DIR")
echo "   File: $FILE_PERMS"
echo "   Directory: $DIR_PERMS"

# Check if www-data can read
if [ -r "$FULL_PATH" ]; then
    echo "   ✓ File is readable"
else
    echo "   ✗ File is NOT readable (check permissions)"
fi

echo ""

# Check Apache configuration
echo "3. Checking Apache configuration..."
if grep -q "Alias /media" /etc/apache2/sites-enabled/*.conf 2>/dev/null; then
    echo "   ✓ Alias /media found in Apache config"
    grep "Alias /media" /etc/apache2/sites-enabled/*.conf | head -1
else
    echo "   ✗ Alias /media NOT found in Apache config"
    echo "   → Add: Alias /media /data/var/mcc/media"
fi

if grep -q "ProxyPass /media/ !" /etc/apache2/sites-enabled/*.conf 2>/dev/null; then
    echo "   ✓ ProxyPass /media/ ! found in Apache config"
    grep "ProxyPass /media/ !" /etc/apache2/sites-enabled/*.conf | head -1
else
    echo "   ✗ ProxyPass /media/ ! NOT found in Apache config"
    echo "   → Add: ProxyPass /media/ ! (BEFORE ProxyPass /)"
fi

echo ""

# Test Apache config syntax
echo "4. Testing Apache configuration syntax..."
if sudo apache2ctl configtest 2>&1 | grep -q "Syntax OK"; then
    echo "   ✓ Apache configuration syntax is OK"
else
    echo "   ✗ Apache configuration has syntax errors:"
    sudo apache2ctl configtest 2>&1 | grep -v "^Syntax OK"
fi

echo ""

# Test HTTP access (if server is accessible)
echo "5. Testing HTTP access..."
if command -v curl &> /dev/null; then
    URL="https://mycyclingcity.net/media/group_logos/${TEST_FILE}"
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$URL" 2>/dev/null || echo "000")
    
    if [ "$HTTP_CODE" = "200" ]; then
        echo "   ✓ HTTP access OK (200)"
    elif [ "$HTTP_CODE" = "404" ]; then
        echo "   ✗ HTTP access failed (404 Not Found)"
        echo "   → Apache is not serving /media/ correctly"
    elif [ "$HTTP_CODE" = "403" ]; then
        echo "   ✗ HTTP access failed (403 Forbidden)"
        echo "   → Check file permissions"
    elif [ "$HTTP_CODE" = "000" ]; then
        echo "   ? Could not test HTTP access (curl failed or server unreachable)"
    else
        echo "   ? HTTP access returned: $HTTP_CODE"
    fi
else
    echo "   ? curl not available, skipping HTTP test"
fi

echo ""
echo "=== Test Complete ==="
