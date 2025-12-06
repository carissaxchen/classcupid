#!/usr/bin/env python3
"""
Migration script to add term_preference field to User table
Run this after updating models.py
"""

import sqlite3
import sys
import os

# Try instance directory first (Flask default), then root directory
if os.path.exists("instance/classcupid.db"):
    DB_PATH = "instance/classcupid.db"
elif os.path.exists("classcupid.db"):
    DB_PATH = "classcupid.db"
else:
    print("Error: Could not find classcupid.db in instance/ or root directory")
    sys.exit(1)

def migrate():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        print("Adding term_preference column to users table...")
        try:
            cursor.execute("ALTER TABLE users ADD COLUMN term_preference VARCHAR(20)")
            print("✓ Added term_preference column")
        except sqlite3.OperationalError as e:
            if "duplicate column" in str(e).lower():
                print("  term_preference column already exists")
            else:
                raise
        
        conn.commit()
        print("\n✓ Migration completed successfully!")
        
    except Exception as e:
        conn.rollback()
        print(f"\n✗ Migration failed: {e}")
        sys.exit(1)
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()

