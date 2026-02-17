#!/usr/bin/env python3
"""Convert Python files from UTF-16 to UTF-8 encoding"""

from pathlib import Path

files_to_fix = [
    'web/views/__init__.py',
    'web/views/helpers.py',
    'web/constants.py',
    'web/scoring.py'
]

for file_path in files_to_fix:
    path = Path(file_path)
    if not path.exists():
        print(f"File not found: {file_path}")
        continue
    
    try:
        # Try to read as UTF-16
        with open(path, 'r', encoding='utf-16') as f:
            content = f.read()
        print(f"Detected UTF-16: {file_path}")
    except UnicodeDecodeError:
        try:
            # Try UTF-8
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
            print(f"Already UTF-8: {file_path}")
            continue
        except Exception as e:
            print(f"Error reading {file_path}: {e}")
            continue
    
    # Write as UTF-8
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(content)
    print(f"Converted to UTF-8: {file_path}")

print("\nAll files converted!")
