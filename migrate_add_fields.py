#!/usr/bin/env python3
"""
Migration script to add new fields to User and Course tables
Run this after updating models.py
"""

import sqlite3
import sys

DB_PATH = "classcupid.db"

def migrate():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        # Add new columns to users table
        print("Adding affiliation column to users table...")
        try:
            cursor.execute("ALTER TABLE users ADD COLUMN affiliation VARCHAR(50)")
            print("✓ Added affiliation column")
        except sqlite3.OperationalError as e:
            if "duplicate column" in str(e).lower():
                print("  affiliation column already exists")
            else:
                raise
        
        print("Adding school_preferences column to users table...")
        try:
            cursor.execute("ALTER TABLE users ADD COLUMN school_preferences TEXT")
            print("✓ Added school_preferences column")
        except sqlite3.OperationalError as e:
            if "duplicate column" in str(e).lower():
                print("  school_preferences column already exists")
            else:
                raise
        
        # Add new columns to courses table
        print("Adding class_level_attribute_description column to courses table...")
        try:
            cursor.execute("ALTER TABLE courses ADD COLUMN class_level_attribute_description VARCHAR(200)")
            print("✓ Added class_level_attribute_description column")
        except sqlite3.OperationalError as e:
            if "duplicate column" in str(e).lower():
                print("  class_level_attribute_description column already exists")
            else:
                raise
        
        print("Adding course_component column to courses table...")
        try:
            cursor.execute("ALTER TABLE courses ADD COLUMN course_component VARCHAR(100)")
            print("✓ Added course_component column")
        except sqlite3.OperationalError as e:
            if "duplicate column" in str(e).lower():
                print("  course_component column already exists")
            else:
                raise
        
        print("Adding subject_description column to courses table...")
        try:
            cursor.execute("ALTER TABLE courses ADD COLUMN subject_description VARCHAR(200)")
            print("✓ Added subject_description column")
        except sqlite3.OperationalError as e:
            if "duplicate column" in str(e).lower():
                print("  subject_description column already exists")
            else:
                raise
        
        print("Adding catalog_school_description column to courses table...")
        try:
            cursor.execute("ALTER TABLE courses ADD COLUMN catalog_school_description VARCHAR(200)")
            print("✓ Added catalog_school_description column")
        except sqlite3.OperationalError as e:
            if "duplicate column" in str(e).lower():
                print("  catalog_school_description column already exists")
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

