#!/bin/bash
# Helper script to update the GROW_BEARER_TOKEN in .env

if [ -z "$1" ]; then
    echo "Usage: ./update_token.sh <new-bearer-token>"
    echo ""
    echo "Example:"
    echo "  ./update_token.sh eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
    echo ""
    echo "This will update GROW_BEARER_TOKEN in your .env file"
    exit 1
fi

NEW_TOKEN="$1"

# Backup .env
cp .env .env.backup

# Update the token
if grep -q "^GROW_BEARER_TOKEN=" .env; then
    # Token exists, replace it
    sed -i.bak "s|^GROW_BEARER_TOKEN=.*|GROW_BEARER_TOKEN=$NEW_TOKEN|" .env
    echo "✓ Updated GROW_BEARER_TOKEN in .env"
else
    # Token doesn't exist, add it
    echo "" >> .env
    echo "GROW_BEARER_TOKEN=$NEW_TOKEN" >> .env
    echo "✓ Added GROW_BEARER_TOKEN to .env"
fi

# Verify it worked
if grep -q "^GROW_BEARER_TOKEN=$NEW_TOKEN" .env; then
    echo "✓ Token updated successfully"
    rm .env.bak 2>/dev/null
else
    echo "✗ Token update failed, restoring backup"
    mv .env.backup .env
    exit 1
fi
