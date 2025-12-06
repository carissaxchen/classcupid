"""Migration script to add class_level_attribute column"""
from app import app, db
from sqlalchemy import text

with app.app_context():
    try:
        with db.engine.connect() as conn:
            # Check courses table
            result = conn.execute(text("PRAGMA table_info(courses)"))
            columns = [row[1] for row in result]
            
            if 'class_level_attribute' not in columns:
                print("Adding 'class_level_attribute' column...")
                conn.execute(text("ALTER TABLE courses ADD COLUMN class_level_attribute VARCHAR(100)"))
                conn.commit()
                print("Migration completed successfully!")
            else:
                print("Column 'class_level_attribute' already exists.")
    except Exception as e:
        print(f"Error during migration: {e}")
        import traceback
        traceback.print_exc()

