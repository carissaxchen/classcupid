# Class Cupid

A dating app-style course selection web app for Harvard students. Discover courses by swiping, save your favorites, and rank them through an interactive comparison game.

## Features

- **Discover Page**: Swipe through courses personalized to your preferences (heart, star, or discard)
- **Matches Page**: Compare saved courses in a sorting game to create your personalized ranking
- **Profile Page**: Set your year, affiliation, concentration interests, requirements, and term preferences
- **Smart Filtering**: Course recommendations based on year level, concentration, Gen Ed categories, divisional distributions, language requirements, and more
- **Multi-Semester Support**: View and compare courses from different semesters separately
- **Binary Search Ranking**: Advanced algorithm ranks your saved courses based on pairwise comparisons

## Requirements

- Python 3.8 or higher
- pip (Python package manager)

## Setup

### 1. Install Dependencies

Install all required Python packages:

```bash
pip install -r requirements.txt
```

This will install:
- Flask 3.0.0 (web framework)
- Flask-SQLAlchemy 3.1.1 (database ORM)
- Flask-Session 0.5.0 (session management)
- Werkzeug 3.0.1 (security utilities)
- SQLAlchemy 2.0.23 (database toolkit)
- Click 8.1.7 (CLI framework)

### 2. Initialize the Database

The database will be created automatically when you first run the application. To explicitly create it:

```bash
python app.py
```

This creates the SQLite database file at `instance/classcupid.db` with all necessary tables (users, courses, user_course_preferences, sort_comparisons).

**Note**: If you need to recreate the database from scratch, delete the `instance/classcupid.db` file and run the above command again.

### 3. Import Course Data

Import course catalog data from JSON files. You can import multiple semesters:

```bash
# Import Fall 2025 courses
flask import-courses 2025_Fall_courses.json

# Import Spring 2026 courses
flask import-courses 2026_Spring_courses.json
```

The import command will:
- Parse the JSON file and extract course information
- Check for existing courses (by course ID and term) and update them if found
- Import new courses if they don't exist
- Display a summary: `Import complete: X imported, Y updated, Z skipped`

**Important**: The same course can exist in multiple semesters (e.g., a course offered in both Fall and Spring). Each semester's version is stored separately.

### 4. Run the Application

Start the Flask development server:

```bash
flask run
```

Or alternatively:

```bash
python app.py
```

The application will start on `http://localhost:5000` (default Flask port). If port 5000 is already in use, Flask will automatically use the next available port and display it in the terminal.

### 5. Access the Application

Open your web browser and navigate to:

```
http://localhost:5000
```

## Usage Guide

### First-Time Setup

1. **Register an Account**: Click "Register" on the login page and create a username and password.

2. **Set Your Profile** (required before using Discover):
   - Select your affiliation: "Harvard College" or "Other Affiliation"
   - Choose your year: Freshman, Sophomore, Junior, or Senior
   - Select which term(s) you want to see courses for: "2025 Fall", "2026 Spring", or both
   - (Harvard College only) Select concentration interests (you can select multiple)
   - (Harvard College only) Select requirements to fulfill:
     - Gen Ed categories (Science & Technology in Society, Aesthetics & Culture, Ethics & Civics, Histories, Societies, Individuals)
     - Divisional distributions (Arts and Humanities, Social Sciences, Science and Engineering and Applied Science)
     - Language Requirement (only shows introductory language courses)
     - First Year Seminar (only for freshmen)
     - Quantitative Reasoning
   - (Other Affiliation only) Select your graduate school(s)
   - Click "Update Profile" to save your preferences

### Discovering Courses

1. Navigate to the **Discover** page from the navigation bar.

2. You'll see a course card with:
   - Course number and title
   - Instructor name
   - Department
   - Meeting times and days
   - Course description

3. Take action on the course:
   - **Heart (♥)**: Save the course for later (appears in Matches)
   - **Star (★)**: Mark as a favorite (also appears in Matches, sorted above hearted courses)
   - **X (✕)**: Discard the course
   - **Undo (←)**: Undo your last action and return to that course

4. The algorithm will show you courses based on your profile preferences. If you run out of relevant courses, you'll see a prompt to either:
   - Go to Matches to rank your saved courses
   - Update your profile to add more subjects/requirements

### Ranking Your Saved Courses

1. Navigate to the **Matches** page after you've saved some courses (hearted or starred).

2. **Comparison Game**:
   - You'll see two course cards side-by-side
   - Click anywhere on a card to select it as your preference
   - Click "Skip →" to skip the comparison
   - Click "← Undo" to undo your last comparison

3. **Ranked List**:
   - After making a sufficient number of comparisons (minimum 3, or up to 10 depending on how many courses you have), a "Show Ranked List" button will appear
   - Click it to see your courses ranked from 1st favorite to least favorite
   - The ranking is calculated using a binary search algorithm based on your comparisons
   - Starred courses always appear above hearted courses, regardless of ranking

4. **Managing Saved Courses**:
   - In the ranked list, you can:
     - Click the star icon to toggle favorite status (yellow = favorited)
     - Click the heart icon to toggle saved status
     - Click the X icon to remove the course from your saved list
   - Course names are hyperlinked to the official Harvard course catalog page

5. **Multi-Semester Ranking**:
   - If you've selected multiple terms, courses from different semesters are ranked separately
   - You can only compare courses from the same semester
   - Each semester has its own progress tracking and ranking

### Updating Your Profile

- Visit the **Profile** page anytime to update your preferences
- Changes take effect immediately on the Discover page
- Use the "Reset All Choices" button to clear all your swipes and comparisons and start fresh

## How Course Filtering Works

### For Harvard College Students

The recommendation algorithm filters courses based on:

1. **Year Level**: 
   - Freshmen: Heavy preference for introductory courses (1-99, 1000-1099), moderate preference for mid-level (100-199, 1100-1999)
   - Sophomores: Balanced preference for intro and mid-level courses, access to sophomore tutorials
   - Juniors: Low preference for intro courses, high preference for mid-level and graduate courses (200-299, 2000-2999)
   - Seniors: Very low preference for intro courses, high preference for mid-level and graduate courses, access to senior tutorials

2. **Concentration**: If selected, only shows courses from those departments

3. **Gen Ed Categories**: Uses external JSON files to find specific course codes (e.g., "GENED 1145") matching selected categories. Gen Eds are open to all grade levels.

4. **Divisional Distribution**: Filters by Arts & Humanities, Social Sciences, or Science & Engineering. Excludes Tutorial courses.

5. **Language Requirement**: Only shows introductory language courses (levels 1, 2, 3, A, B, AA, BA)

6. **First Year Seminar**: Special filter for FYSEMR courses (only for freshmen)

### For Other Affiliation Students

The algorithm uses school-specific filtering based on `catalogSchoolDescription`:

- **Graduate School of Arts and Sciences**: Faculty of Arts & Sciences courses with numbers 200-299, 300-399, 2000-2999, or 3000-3999
- **Harvard Business School**: Courses where catalog school description includes "Business School"
- Other graduate schools: Exact match with catalog school description

## Database

The application uses SQLite with SQLAlchemy ORM. The database file is located at:

```
instance/classcupid.db
```

### Database Schema

- **users**: User accounts and preferences
- **courses**: Course catalog data (can have multiple entries per course for different semesters)
- **user_course_preferences**: Tracks heart/star/discard actions
- **sort_comparisons**: Stores pairwise comparisons from the matching game

### Backup and Recovery

The database is automatically backed up to the `backups/` directory when you run certain commands. To manually backup:

```bash
cp instance/classcupid.db backups/classcupid_backup_$(date +%Y%m%d_%H%M%S).db
```

To restore from a backup, stop the application and replace the database file:

```bash
cp backups/classcupid_backup_YYYYMMDD_HHMMSS.db instance/classcupid.db
```

## Troubleshooting

### No courses appearing on Discover page

1. **Check your profile**: Make sure you've selected at least one term preference. Go to Profile and verify your selections.

2. **Check course data**: Verify that courses have been imported:
   ```bash
   # Check the database (requires sqlite3 command-line tool)
   sqlite3 instance/classcupid.db "SELECT COUNT(*) FROM courses;"
   ```

3. **Check your preferences**: Very specific filtering (e.g., single concentration + multiple requirements) may result in few or no matches. Try expanding your selections.

### "Your session has expired" error

This occurs if the database was recreated and your user account no longer exists. Simply log out and register a new account, or log back in if your account still exists.

### Import errors

- **File not found**: Make sure the JSON file is in the project root directory
- **JSON parsing errors**: Verify the JSON file is valid JSON format
- **Database locked**: Stop the Flask application, then try importing again

### Port already in use

If port 5000 is busy, Flask will automatically use another port. Check the terminal output for the actual port number, or specify a different port:

```bash
flask run --port 5001
```

### Database migration issues

If you've updated the code and need to add new columns to existing tables, you may need to run migration scripts or recreate the database:

1. Back up your data (if needed)
2. Delete `instance/classcupid.db`
3. Run `python app.py` to recreate tables
4. Re-import course data using `flask import-courses`

## Project Structure

```
class_cupidv1/
├── app.py                          # Main Flask application
├── models.py                       # Database models (User, Course, etc.)
├── helpers.py                      # Utility functions
├── requirements.txt                # Python dependencies
├── README.md                       # This file
├── DESIGN.md                       # Technical design document
├── templates/                      # HTML templates
│   ├── base.html
│   ├── login.html
│   ├── register.html
│   ├── profile.html
│   ├── discover.html
│   └── matches.html
├── static/
│   ├── css/
│   │   └── style.css              # Global styles
│   └── js/
│       └── main.js                # Client-side JavaScript
├── instance/
│   └── classcupid.db              # SQLite database (created at runtime)
├── 2025_Fall_courses.json         # Fall 2025 course catalog
├── 2026_Spring_courses.json       # Spring 2026 course catalog
├── 2025_Fall_Geneds.json          # Fall 2025 Gen Ed mappings
├── 2026_Spring_Geneds.json        # Spring 2026 Gen Ed mappings
├── harvard_college_concentrations.json
└── harvard_schools.json
```

## Additional Notes

- **Course Data**: Course information is imported from Harvard's course catalog JSON files. These files should be updated each semester.

- **Gen Ed Categories**: Gen Ed category mappings are stored in separate JSON files (`*_Geneds.json`). These files map categories to specific course codes.

- **QReports Quotes**: Course quotes from QReports can be added by updating the `quotes_json` field in the Course model (requires database access).

- **Font**: The application uses the Apple system font family for consistent typography.

- **Session Storage**: User sessions are stored in the `flask_session/` directory as files. You can clear all sessions by deleting files in this directory.

For technical implementation details, see `DESIGN.md`.

