#!/bin/bash
cd /opt/shamrock-fantasy

# Temporarily patch settings to remove silk
cp config/settings.py config/settings.py.backup

# Run migrations by removing silk from INSTALLED_APPS temporarily
python3 << 'PYEOF'
import os
import sys

# Read the file
with open('config/settings.py', 'r') as f:
    content = f.read()

# Comment out silk if present
content = content.replace("'silk',", "# 'silk',  # Temporarily commented for migration")
content = content.replace('"silk",', '# "silk",  # Temporarily commented for migration')

# Write it back
with open('config/settings.py', 'w') as f:
    f.write(content)
PYEOF

# Run migrations
python3 manage.py migrate --run-syncdb

# Restore original settings
mv config/settings.py.backup config/settings.py

echo "Migrations completed successfully!"
