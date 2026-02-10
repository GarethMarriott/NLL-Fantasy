#!/usr/bin/env python3
import os
import sys
import sqlite3

# Add the project to path
sys.path.insert(0, '/opt/shamrock-fantasy')

# Direct SQL approach - add the column if it doesn't exist
db_path = '/opt/shamrock-fantasy/db.sqlite3'

try:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Check if column already exists
    cursor.execute("PRAGMA table_info(web_futurerookiepick)")
    columns = [column[1] for column in cursor.fetchall()]
    
    if 'order_finalized' not in columns:
        print("Adding order_finalized column to web_futurerookiepick...")
        cursor.execute("""
            ALTER TABLE web_futurerookiepick 
            ADD COLUMN order_finalized BOOLEAN DEFAULT 0
        """)
        conn.commit()
        print("✓ Column added successfully")
    else:
        print("✓ order_finalized column already exists")
    
    conn.close()
    print("Migration completed!")
    
except Exception as e:
    print(f"Error: {e}")
    sys.exit(1)
