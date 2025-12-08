# Class Cupid

A dating app-style course selection web app for Harvard students. Discover courses by swiping, save your favorites, and rank them through an interactive comparison game.

## Video Demo

Watch a demonstration of Class Cupid in action: [YouTube Video](https://youtu.be/31axDUmNUz8?si=h2u6JnydmZzS9eC_)

## Features

- **Discover Page**: Swipe through courses personalized to your preferences (heart, star, or discard)
- **Matches Page**: Compare saved courses in a sorting game to create your personalized ranking
- **Settings Page**: Configure your year, affiliation, concentration interests, requirements, and term preferences
- **Smart Filtering**: Course recommendations based on year level, concentration, Gen Ed categories, divisional distributions, language requirements, and more
- **Multi-Semester Support**: View and compare courses from different semesters separately
- **Binary Search Ranking**: Advanced algorithm ranks your saved courses based on pairwise comparisons
- **Undo Functionality**: Undo your last action on both Discover and Matches pages

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
- Flask 2.3.3 (web framework)
- Flask-SQLAlchemy 3.1.1 (database ORM)
- Flask-Session 0.5.0 (session management)
- Werkzeug 2.3.8 (security utilities)
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
flask import-courses data/json/2025_Fall_courses.json

# Import Spring 2026 courses
flask import-courses data/json/2026_Spring_courses.json
```

The import command will:
- Parse the JSON file and extract course information
- Check for existing courses (by course ID and term) and update them if found
- Import new courses if they don't exist
- Display a summary: `Import complete: X imported, Y updated, Z skipped`

**Important**: The same course can exist in multiple semesters (e.g., a course offered in both Fall and Spring). Each semester's version is stored separately using a composite unique constraint on `(course_id, term_description)`.

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

2. **Configure Your Settings** (required before using Discover):
   - Click on your username in the navigation bar (or "Profile" if not yet logged in)
   - Select your affiliation: "Harvard College" or "Other Affiliation"
   - **Select term(s)**: Choose "2025 Fall", "2026 Spring", or both (you can select multiple)
   - If "Harvard College":
     - Choose your year: Freshman, Sophomore, Junior, or Senior
     - Select concentration interests (you can select multiple, or use "Select all")
     - Select requirements to fulfill:
       - **Gen Ed categories**: Science & Technology in Society, Aesthetics & Culture, Ethics & Civics, Histories, Societies, Individuals
       - **Divisional distributions**: Arts and Humanities, Social Sciences, Science and Engineering and Applied Science
         - *Info icon*: Click the (i) icon to see that selecting a division will show ALL concentrations within that division
       - **Language Requirement**: Only shows introductory language courses (levels 1, 2, 3, A, B, AA, BA)
       - **First Year Seminar**: Only available for freshmen - shows FYSEMR courses
       - **Quantitative Reasoning**
   - If "Other Affiliation":
     - Select your graduate school(s) - you can select multiple:
       - Graduate School of Arts and Sciences
       - Harvard Business School
       - Harvard School of Dental Medicine
       - Harvard T.H. Chan School of Public Health
       - Graduate School of Design
       - Harvard Divinity School
       - Harvard Graduate School of Education
       - Harvard Kennedy School
       - Harvard Law School
       - Harvard Medical School
   - Click "Update Profile" to save your preferences

### Discovering Courses

1. Navigate to the **Discover** page from the navigation bar (fire icon).

2. **First Visit**: You'll see a welcome popup explaining the action buttons. Click "Got it!" to dismiss it.

3. **Course Card**: You'll see a course card with:
   - Course number and title (hyperlinked to official Harvard course page)
   - Instructor name
   - Department
   - Meeting times and days (displayed as day abbreviations like "MWF")
   - Course description
   - Course metadata (credits, enrollment, etc.)

4. **Take Action** (buttons arranged horizontally):
   - **← Undo** (light blue): Undo your last action and return to that specific course
   - **✕ Discard**: Remove the course from your feed
   - **♥ Heart**: Save the course for later (appears in Matches)
   - **★ Star** (yellow when active): Mark as a favorite (also appears in Matches, sorted above hearted courses)

5. **Course Recommendations**: The algorithm shows courses based on your profile preferences using weighted selection:
   - Courses appropriate for your year level are weighted higher (more likely to appear)
   - Once you swipe a course (any action), it won't appear again until you reset your choices
   - If you run out of relevant courses, you'll see a prompt to either:
     - Go to Matches to rank your saved courses
     - Update your Settings to add more subjects/requirements

### Ranking Your Saved Courses

1. Navigate to the **Matches** page (compass icon) after you've saved some courses (hearted or starred).

2. **Comparison Game**:
   - You'll see two course cards side-by-side with course details
   - **Click anywhere on a card** to select it as your preference (winner)
   - Click **"Skip →"** to skip the comparison and see a new pair
   - Click **"← Undo"** to undo your last comparison
   - Courses must be from the same semester to be compared

3. **Progress Tracking**:
   - You'll see a message indicating how many comparisons you've made
   - The minimum number of comparisons needed is `max(3, min(10, total_courses - 1))`:
     - Minimum: 3 comparisons
     - Maximum: 10 comparisons
     - Scales with course count in between

4. **Ranked List**:
   - After making sufficient comparisons, your courses are automatically ranked
   - Rankings are displayed with numbers (1, 2, 3...) in a leftmost column
   - The ranking uses a binary search algorithm that learns from your pairwise comparisons
   - **Display Order**:
     - Before ranking: Starred courses first, then hearted courses, sorted by course number
     - After ranking: Courses displayed by rank (position 1 = favorite), but starred courses still appear above hearted courses

5. **Managing Saved Courses**:
   - In the saved classes list, you can:
     - Click the **star icon** (★) to toggle favorite status (yellow = favorited)
     - Click the **heart icon** (♥) to toggle saved status
     - Click the **X icon** (✕) to remove the course from your saved list
   - Course names are hyperlinked to the official Harvard course catalog page

6. **Multi-Semester Ranking**:
   - If you've selected multiple terms, courses from different semesters are ranked separately
   - You can only compare courses from the same semester (prevents meaningless cross-semester comparisons)
   - Each semester has its own progress tracking and ranking

### Updating Your Settings

- Click on your **username** in the navigation bar to access Settings
- Update any preferences - changes take effect immediately on the Discover page
- Use the **"Reset All Choices"** button at the bottom to clear all your swipes and comparisons and start fresh

## How Course Filtering Works

### For Harvard College Students

The recommendation algorithm uses a multi-stage weighted selection process:

1. **Term Filtering**: Only shows courses from your selected terms

2. **Year-Level Appropriate Weighting**: 
   - **Freshmen**: Heavy preference for introductory courses (1-99, 1000-1099), moderate for mid-level (100-199, 1100-1999). Cannot see graduate courses, tutorials, or reading/research classes. First Year Seminars weighted at 1 (low frequency).
   - **Sophomores**: Balanced preference for intro and mid-level courses. Can access sophomore tutorials, special seminars (96, 960), and reading/research (91, 910).
   - **Juniors**: Low preference for intro courses, high preference for mid-level and graduate-level courses (200-299, 2000-2999). Can access junior tutorials, special seminars, and reading/research.
   - **Seniors**: Very low preference for intro courses, high preference for mid-level and graduate courses. Can access senior tutorials, special seminars, and reading/research.

3. **Concentration Filtering**: If selected, shows courses from those departments. Can select multiple concentrations or use "Select all".

4. **Gen Ed Categories**: Uses external JSON files (`data/json/*_Geneds.json`) to find specific course codes (e.g., "GENED 1145") matching selected categories. **Important**: Gen Eds are open to all grade levels - grade-level restrictions are bypassed for Gen Ed courses.

5. **Divisional Distribution**: Filters by Arts & Humanities, Social Sciences, or Science & Engineering. **Excludes Tutorial courses**. Click the (i) info icon to see that selecting a division will show ALL concentrations within that division.

6. **Language Requirement**: Only shows introductory language courses identified by:
   - Department prefixes (FRENCH, SPANISH, CHINESE, GERMAN, etc.)
   - Course number patterns: 1, 2, 3, A, B, AA, BA
   - **Note**: Some departments have different language requirement metrics (e.g., Chinese requires scoring above 130, which may require numbered classes). Advanced language courses can be found by selecting specific language concentrations.

7. **First Year Seminar**: Special filter for courses with `catalogSubject = "FYSEMR"`. Only freshmen can see these. Uses **union logic** - if you select FYSEMR + a concentration, you'll see all FYSEMR courses OR all courses in that concentration (not just FYSEMR courses in that concentration).

8. **Alpha Courses**: Language courses, composition courses, and Gen Eds that are open to all years. Weighted consistently across all years.

### For Other Affiliation Students

The algorithm uses completely different school-specific filtering (no year-based weighting):

- **Graduate School of Arts and Sciences**: Shows courses where:
  - `catalogSchoolDescription = "Faculty of Arts & Sciences"` AND
  - Course number is in ranges: 200-299, 300-399, 2000-2999, or 3000-3999

- **Harvard Business School**: Shows courses where `catalogSchoolDescription` includes "Business School" (matches both "Business School Doctoral" and "Business School MBA")

- **Harvard School of Dental Medicine**: Shows courses where `catalogSchoolDescription = "School of Dental Medicine"`

- **Harvard T.H. Chan School of Public Health**: Shows courses where `catalogSchoolDescription = "Harvard Chan School"`

- **Other Graduate Schools** (Design, Divinity, Education, Kennedy, Law, Medical): Exact string match with `catalogSchoolDescription`

### Course Exclusion After Swiping

Once you swipe a course (heart, star, or discard), it is **permanently removed** from your recommendation pool. This ensures you never see the same course twice. The course will only reappear if you:
- Use the "Reset All Choices" button in Settings, or
- The database is reset

## Database

The application uses SQLite with SQLAlchemy ORM. The database file is located at:

```
instance/classcupid.db
```

### Database Schema

- **users**: User accounts and preferences (stored as JSON arrays)
- **courses**: Course catalog data (can have multiple entries per course for different semesters)
- **user_course_preferences**: Tracks heart/star/discard actions with timestamps
- **sort_comparisons**: Stores pairwise comparisons from the matching game with timestamps

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

1. **Check your Settings**: Make sure you've selected at least one term preference. Click your username → Settings and verify your selections.

2. **Check course data**: Verify that courses have been imported:
   ```bash
   # Check the database (requires sqlite3 command-line tool)
   sqlite3 instance/classcupid.db "SELECT COUNT(*) FROM courses;"
   ```

3. **Check your preferences**: Very specific filtering (e.g., single concentration + multiple requirements) may result in few or no matches. Try expanding your selections.

4. **All courses already swiped**: If you've swiped through all available courses, you'll see a message prompting you to either check Matches or update your Settings.

### "Your session has expired" error

This occurs if the database was recreated and your user account no longer exists. Simply log out and register a new account, or log back in if your account still exists.

### Import errors

- **File not found**: Make sure the JSON file is in the `data/json/` directory and use the full path: `flask import-courses data/json/FILENAME.json`
- **JSON parsing errors**: Verify the JSON file is valid JSON format
- **Database locked**: Stop the Flask application, then try importing again

### Port already in use

If port 5000 is busy, Flask will automatically use another port. Check the terminal output for the actual port number, or specify a different port:

```bash
flask run --port 5001
```

### Database migration issues

If you've updated the code and need to add new columns to existing tables, you may need to recreate the database:

1. Back up your data (if needed): `cp instance/classcupid.db backups/backup.db`
2. Delete `instance/classcupid.db`
3. Run `python app.py` to recreate tables
4. Re-import course data using `flask import-courses data/json/2025_Fall_courses.json` (and Spring if needed)

## Project Structure

```
class_cupidv1/
├── app.py                          # Main Flask application (routes, algorithms, CLI commands)
├── models.py                       # Database models (User, Course, UserCoursePreference, SortComparison)
├── helpers.py                      # Utility functions (login_required decorator, apology helper)
├── requirements.txt                # Python dependencies
├── README.md                       # This file (user manual)
├── DESIGN.md                       # Technical design document
├── templates/                      # HTML templates
│   ├── base.html                  # Base template with navigation, footer, flash messages
│   ├── login.html                 # Authentication page
│   ├── register.html              # User registration
│   ├── profile.html               # Settings/preferences page
│   ├── discover.html              # Course discovery (swipe interface)
│   └── matches.html               # Comparison game and saved courses list
├── static/
│   ├── css/
│   │   └── style.css              # Global styles (Apple system font, responsive layout)
│   ├── js/
│   │   └── main.js                # Client-side JavaScript (tooltips, popup dismissal)
│   └── images/
│       ├── icons/                 # Navigation icons (fire, compass, user-circle)
│       ├── Class Cupid Logo V3-3.png  # Header logo and favicon
│       ├── Class Cupid Text-4.png     # Header text logo
│       └── Class Cupid Logo.png       # Footer logo
├── data/                          # Organized data files
│   ├── images/                    # Logo files and icons (duplicates from root)
│   └── json/                      # Course catalogs and reference data
│       ├── 2025_Fall_courses.json
│       ├── 2026_Spring_courses.json
│       ├── 2025_Fall_Geneds.json
│       ├── 2026_Spring_Geneds.json
│       ├── harvard_college_concentrations.json
│       └── harvard_schools.json
├── instance/
│   └── classcupid.db              # SQLite database (created at runtime)
├── flask_session/                 # Session files (created at runtime)
└── backups/                       # Database backups (created as needed)
```

## Additional Notes

- **Course Data**: Course information is imported from Harvard's course catalog JSON files. These files should be updated each semester and placed in `data/json/`.

- **Gen Ed Categories**: Gen Ed category mappings are stored in separate JSON files (`data/json/*_Geneds.json`). These files map categories to specific course codes (e.g., "GENED 1145").

- **Font and Styling**: The application uses the Apple system font family for consistent typography across devices. The background features a subtle pattern for visual interest.

- **Session Storage**: User sessions are stored in the `flask_session/` directory as files. You can clear all sessions by deleting files in this directory.

- **Logo and Branding**: The Class Cupid logo appears in the header (with text) and as a favicon. A footer logo appears at the bottom of pages with copyright information.

- **Error Handling**: Error messages are displayed directly on login/register pages using flash messages (not separate error pages) for better user experience.

For detailed technical implementation information, algorithms, and architecture decisions, see `DESIGN.md`.

---

**Code © 2025 Carissa Chen and Haotian Pan**  
**Course metadata © 2025-2026 President and Fellows of Harvard College**
