# Design Document: Class Cupid

## Overview

Class Cupid is a Flask-based web application that helps Harvard students discover and rank courses through a dating app-style discovery interface and a binary search-based comparison game. The system intelligently filters courses based on user preferences (year, concentration, requirements, term) and employs sophisticated algorithms to ensure course recommendations are appropriate and relevant.

## Architecture

### Technology Stack

- **Backend Framework**: Flask 3.0.0 with Flask-SQLAlchemy for ORM
- **Database**: SQLite (development) with SQLAlchemy ORM layer
- **Session Management**: Flask-Session with filesystem storage
- **Authentication**: Werkzeug password hashing with SHA-256
- **Frontend**: Jinja2 templating with vanilla JavaScript and CSS
- **Font**: Inter (Google Fonts) for consistent typography

### Application Structure

The application follows a traditional MVC (Model-View-Controller) pattern:

- **Models** (`models.py`): SQLAlchemy ORM models defining database schema
- **Views** (`templates/`): Jinja2 HTML templates for UI rendering
- **Controllers** (`app.py`): Flask routes handling business logic and request routing
- **Static Assets** (`static/`): CSS stylesheets and JavaScript files
- **Helpers** (`helpers.py`): Utility functions (login decorator, error handling)

## Database Design

### Schema Overview

The database uses four primary tables with carefully designed relationships:

#### 1. `users` Table

Stores user authentication and preference data:

- **Primary Key**: `id` (Integer, auto-increment)
- **Authentication**: `username` (unique), `password_hash`
- **Preferences**: Stored as JSON strings in `Text` columns for flexibility:
  - `term_preference`: JSON array of selected terms (e.g., `["2025 Fall", "2026 Spring"]`)
  - `concentration_preferences`: JSON array of concentration names
  - `requirement_preferences`: JSON array of requirement names
  - `school_preferences`: JSON array for "Other Affiliation" users
- **Profile**: `affiliation` (Harvard College/Other), `year` (Freshman/Sophomore/Junior/Senior)

**Design Decision**: Using JSON storage for preferences allows for easy extensibility without schema migrations. The `get_concentrations()`, `get_requirements()`, `get_schools()`, and `get_terms()` methods provide backward compatibility with comma-separated string formats.

#### 2. `courses` Table

Stores course information from Harvard's course catalog JSON:

- **Primary Key**: `id` (Integer, auto-increment)
- **Composite Unique Constraint**: `(course_id, term_description)` - allows the same course to exist across multiple semesters
- **Course Identification**: `course_id` (from catalog), `course_number` (e.g., "COMPSCI 50"), `term_description` (e.g., "2025 Fall")
- **Metadata**: `course_title`, `instructor_name`, `department`, `course_url`, `description`
- **Scheduling**: `start_time`, `end_time`, `days_of_week`
- **Requirement Flags**: Boolean columns for Gen Ed categories, divisional distributions, language requirement, etc.
- **Classification Fields**: `class_level_attribute`, `catalog_school_description`, `course_component`, `catalog_subject`

**Design Decision**: The composite unique constraint on `(course_id, term_description)` enables multi-semester support without duplicating the same course record. This allows users to see courses offered in both Fall and Spring as separate entities in the matching game.

#### 3. `user_course_preferences` Table

Tracks user interactions with courses on the Discover page:

- **Primary Key**: `id`
- **Foreign Keys**: `user_id` → `users.id`, `course_id` → `courses.id`
- **Status**: `heart`, `star`, or `discard`
- **Timestamp**: Automatic UTC timestamp for ordering
- **Unique Constraint**: `(user_id, course_id)` ensures one preference per course

**Design Decision**: The single `status` column with string values (instead of separate boolean columns) simplifies querying and allows easy status updates without complex migrations.

#### 4. `sort_comparisons` Table

Stores pairwise comparisons from the matching game:

- **Primary Key**: `id`
- **Foreign Keys**: `user_id` → `users.id`, `winner_course_id` → `courses.id`, `loser_course_id` → `courses.id`
- **Timestamp**: Automatic UTC timestamp for ordering and undo functionality
- **Unique Constraint**: `(user_id, winner_course_id, loser_course_id)` prevents duplicate comparisons

**Design Decision**: Storing winner/loser as separate foreign keys (instead of a single course pair with a boolean) makes querying more efficient and allows easy lookup of all comparisons involving a specific course.

### Relationships

- **User → UserCoursePreference**: One-to-many with cascade delete (deleting a user removes all preferences)
- **User → SortComparison**: One-to-many with cascade delete
- **Course → UserCoursePreference**: One-to-many
- **Course → SortComparison**: One-to-many (via both `winner_course_id` and `loser_course_id`)

## Core Algorithms

### 1. Course Recommendation Algorithm (`recommend_course_weighted`)

The recommendation system uses a multi-stage filtering and weighted selection process:

#### Stage 1: Base Query Filtering

1. **Term Filtering**: Courses are filtered by the user's selected terms (defaults to "2025 Fall" if none selected)
2. **Seen Course Tracking**: Excludes courses the user has already interacted with (via `seen_course_ids`)
3. **Affiliation-Based Branching**: Different algorithms for "Harvard College" vs. "Other Affiliation" users

#### Stage 2: Harvard College Filtering

For Harvard College students, the algorithm applies complex, hierarchical filtering:

**Concentration Filtering**: If concentrations are selected, courses are filtered by `department` matching the concentration name. If no concentrations are selected, all departments are shown.

**Requirement Filtering**: Two approaches depending on requirement type:
- **Gen Ed Categories** (Science & Technology in Society, Aesthetics & Culture, Ethics & Civics, Histories, Societies, Individuals): Uses external JSON files (`2025_Fall_Geneds.json`, `2026_Spring_Geneds.json`) to map categories to specific course codes (e.g., "GENED 1145"). The system parses these JSON files, strips comments using regex, and builds a set of course numbers to filter by.
- **Other Requirements**: Uses boolean flags on the Course model (divisional distributions, language requirement, etc.)

**First Year Seminar Handling**: Special union logic - if "First Year Seminar" is selected, courses with `catalog_subject = "FYSEMR"` are collected separately and merged with the main query results, bypassing concentration and level filtering.

**Language Requirement**: Pattern-based identification - checks if course number starts with common language prefixes (FRENCH, SPANISH, CHINESE, etc.) and filters for introductory levels (1, 2, 3, A, B, AA, BA).

#### Stage 3: Post-Query Filtering

After initial SQL filtering, Python-level filtering applies grade-appropriate restrictions:

1. **Tutorial Restrictions**: Freshmen cannot see tutorials; upperclassmen can only see their year's tutorial
2. **Reading Research/Special Seminars**: Freshmen excluded; others allowed (96, 960, 91, 910)
3. **Graduate Course Restrictions**: `Grad_research` (300-399, 3000-3999) excluded for all undergraduates
4. **First Year Seminar**: Only freshmen can see FYSEMR courses
5. **Gen Ed Exception**: Gen Ed courses bypass all grade-level filtering (open to all years)
6. **Divisional Distribution**: Tutorial courses excluded when filtering by divisional distribution

**Design Decision**: The two-stage filtering (SQL query + Python post-processing) balances performance (database-level filtering is faster) with flexibility (Python allows complex logic like pattern matching and course number extraction).

#### Stage 4: Course Level Classification

The `classify_level()` method on the Course model categorizes courses:

- **Extraction**: `extract_course_number()` parses numeric values from course numbers (handles "COMPSCI 50" → 50, "MATH 1B" → 1)
- **Classification Rules**:
  - Tutorials: 97/970 (Sophomore), 98/980 (Junior), 99/990 (Senior)
  - Special Seminars: 96/960
  - Reading Research: 91/910
  - Introductory: 1-99, 1000-1099 → `UG_intro`
  - Mid-level: 100-199, 1100-1999 → `UG_mid`
  - Graduate Low: 200-299, 2000-2999 → `Grad_low`
  - Graduate Research: 300-399, 3000-3999 → `Grad_research`
  - Alpha courses: Letter-based (e.g., "ARABIC A") → `Alpha`

**Design Decision**: Using method-based classification (rather than storing level in the database) allows the logic to be centralized and easily updated as course numbering conventions change.

#### Stage 5: Weighted Selection

Courses are weighted based on year and level, then randomly selected from a weighted pool:

- **Freshman**: `UG_intro` (weight 8), `UG_mid` (weight 2), `Alpha` (weight 5)
- **Sophomore**: `UG_intro` (weight 5), `UG_mid` (weight 5), tutorials/seminars/research (weight 2), `Alpha` (weight 5)
- **Junior**: `UG_intro` (weight 2), `UG_mid` (weight 8), `Grad_low` (weight 3), tutorials/seminars/research (weight 2), `Alpha` (weight 5)
- **Senior**: `UG_intro` (weight 1), `UG_mid` (weight 7), `Grad_low` (weight 6), tutorials/seminars/research (weight 2), `Alpha` (weight 5)

**Design Decision**: Weighted selection (adding courses to a pool multiple times based on weight) provides probabilistic ranking while maintaining randomness. This prevents deterministic ordering while still favoring appropriate courses.

#### Stage 6: Other Affiliation Algorithm

For graduate students and other affiliations, completely different filtering applies:

- **School-Specific Filtering**: Uses `filter_courses_for_other_affiliation()` to match `catalog_school_description` to selected schools
- **Special Cases**:
  - Graduate School of Arts and Sciences: Requires `catalog_school_description = "Faculty of Arts & Sciences"` AND course number in ranges 200-299, 300-399, 2000-2999, or 3000-3999 (post-query filtering)
  - Harvard Business School: `catalog_school_description LIKE "%Business School%"`
  - Other schools: Exact string matching
- **No Weighting**: Graduate students see all eligible courses equally (no year-based weighting)

### 2. Binary Search Ranking Algorithm (`rank_courses_binary_search`)

The ranking system uses a binary search insertion sort to create a total ordering from pairwise comparisons:

#### Algorithm Overview

1. **Comparison Graph Building**: Creates a lookup dictionary mapping course pairs to comparison results
2. **Win Count Calculation**: Counts direct wins/losses for each course as a fallback ordering
3. **Binary Search Insertion**: For each course, uses binary search to find its position in a sorted list:
   - Compares the new course to the middle course in the sorted list
   - Uses `is_better()` helper to determine ordering (direct comparison, transitive inference via win count, or unknown)
   - Recursively narrows the search space
4. **Rank Assignment**: Assigns 0-based ranks (0 = best) based on final sorted order

#### Key Design Decisions

- **Binary Search Efficiency**: O(n log n) average case vs. O(n²) for naive insertion sort
- **Transitive Inference**: Uses win counts when direct comparison doesn't exist, improving ranking with sparse comparison data
- **Deterministic Ordering**: With sufficient comparisons, produces a consistent ranking

#### Score Calculation (`calculate_course_scores`)

Converts 0-based ranks to 0-10 scores for internal calculations:
- Best course (rank 0) → score 10
- Worst course (rank n-1) → score approaches 0
- Linear mapping: `score = 10 * (1 - rank / (total - 1))`

**Design Decision**: Scores are calculated but never displayed to users - only ordinal rankings (1, 2, 3...) are shown. This keeps the UI simple while maintaining numerical precision for future algorithmic improvements.

### 3. Semester-Specific Ranking

The matches page maintains separate rankings for each semester:

1. **Term Grouping**: Courses and comparisons are grouped by `term_description`
2. **Isolated Comparisons**: Users can only compare courses from the same term
3. **Separate Rankings**: Binary search ranking is applied per-term, creating independent ordered lists
4. **Progress Tracking**: Minimum comparisons needed and comparison counts are tracked per-term

**Design Decision**: Preventing cross-semester comparisons ensures rankings are meaningful - comparing Fall and Spring courses would be confusing since scheduling, instructors, and availability differ.

## Key Technical Decisions

### 1. Multi-Semester Support

**Challenge**: Same courses can be offered in multiple semesters with different instructors, times, or availability.

**Solution**: Composite unique constraint `(course_id, term_description)` allows duplicate `course_id` values across semesters while preventing true duplicates within a term.

**Impact**: Database queries must always filter by term, and comparisons must validate courses are from the same term.

### 2. JSON-Based Preference Storage

**Challenge**: User preferences need to support arrays (multiple concentrations, requirements, terms) and evolve over time.

**Solution**: Store preferences as JSON strings in `Text` columns with helper methods (`get_concentrations()`, etc.) that parse JSON with fallback to comma-separated strings for backward compatibility.

**Trade-off**: More flexible than normalized tables but requires JSON parsing on every access. Acceptable given the small size of preference arrays.

### 3. Two-Stage Filtering (SQL + Python)

**Challenge**: Complex filtering rules (pattern matching, course number extraction, transitive logic) don't map well to SQL alone.

**Solution**: Use SQLAlchemy for database-level filtering (term, concentration, flags) and Python for complex logic (course number patterns, level classification, grade restrictions).

**Trade-off**: Some courses are filtered out after database retrieval (less efficient) but code remains maintainable and flexible.

### 4. Weighted Selection vs. Deterministic Ranking

**Challenge**: Need to favor appropriate courses while maintaining discovery (users shouldn't see the same courses in the same order every time).

**Solution**: Weighted random selection - courses are added to a pool multiple times based on weight, then randomly selected.

**Trade-off**: Less predictable than strict ranking but more engaging and allows users to discover courses they might otherwise miss.

### 5. Gen Ed Category Mapping

**Challenge**: Gen Ed categories don't map directly to course attributes - they're defined in separate JSON files with specific course codes.

**Solution**: Parse external JSON files (`2025_Fall_Geneds.json`, `2026_Spring_Geneds.json`) at runtime, strip comments with regex, and build a set of course numbers to filter by.

**Trade-off**: Requires file I/O and JSON parsing but keeps Gen Ed definitions external and updatable without code changes.

### 6. Session Management

**Challenge**: Need to track logged-in users across requests without storing sensitive data client-side.

**Solution**: Flask-Session with filesystem storage - session ID stored in cookie, session data (including `user_id`) stored server-side in files.

**Trade-off**: Filesystem storage is simpler than Redis/database sessions but doesn't scale horizontally. Acceptable for single-server deployment.

### 7. Undo Functionality

**Challenge**: Users need to undo actions (swipes, comparisons) but system must handle edge cases (no previous action, database recreation).

**Solution**: 
- **Discover Undo**: Queries most recent `UserCoursePreference` by timestamp, deletes it, and redirects to that specific course via query parameter
- **Matches Undo**: Queries most recent `SortComparison`, deletes it, and redirects to matches page
- **Null Handling**: Graceful error messages if no action exists to undo

**Design Decision**: Using timestamps for ordering ensures chronological undo, and redirecting to specific courses maintains user context.

## File Structure

```
class_cupidv1/
├── app.py                    # Main Flask application (routes, algorithms, CLI commands)
├── models.py                 # SQLAlchemy ORM models (User, Course, UserCoursePreference, SortComparison)
├── helpers.py                # Utility functions (login_required decorator, apology helper)
├── requirements.txt          # Python dependencies
├── README.md                 # User documentation
├── DESIGN.md                 # This file
├── templates/
│   ├── base.html            # Base template with navigation and flash messages
│   ├── login.html           # Authentication page
│   ├── register.html        # User registration
│   ├── profile.html         # Profile setup/preferences
│   ├── discover.html        # Course discovery (swipe interface)
│   └── matches.html         # Comparison game and saved courses list
├── static/
│   ├── css/
│   │   └── style.css        # Global styles (Inter font, responsive layout, component styles)
│   └── js/
│       └── main.js          # Client-side JavaScript (minimal - mostly server-rendered)
├── instance/
│   └── classcupid.db        # SQLite database (created at runtime)
├── flask_session/           # Session files (created at runtime)
├── 2025_Fall_courses.json   # Fall 2025 course catalog
├── 2026_Spring_courses.json # Spring 2026 course catalog
├── 2025_Fall_Geneds.json    # Fall 2025 Gen Ed category mappings
├── 2026_Spring_Geneds.json  # Spring 2026 Gen Ed category mappings
├── harvard_college_concentrations.json  # Available concentrations
└── harvard_schools.json     # Available graduate schools
```

## Data Flow

### Discovery Flow

1. User navigates to `/discover`
2. Route checks user has term preference set (redirects to profile if not)
3. `recommend_course_weighted()` is called:
   - Builds filtered query based on preferences
   - Applies post-query filtering
   - Creates weighted pool
   - Returns random course from pool
4. Template renders course card with action buttons
5. User swipes (heart/star/discard) → POST to `/swipe`
6. `UserCoursePreference` record created/updated
7. Redirect back to `/discover` for next course

### Matching Game Flow

1. User navigates to `/matches`
2. Route fetches saved courses (heart/star) filtered by term
3. Courses grouped by term, comparisons grouped by term
4. For each term:
   - Selects two random courses from same term (avoiding previously compared pairs)
   - Calculates minimum comparisons needed: `max(3, min(10, total_courses - 1))`
   - Checks if ranking should be displayed (comparison_count >= min_comparisons_needed)
5. Template renders comparison cards or ranked list
6. User selects winner → POST to `/matches/compare`
7. `SortComparison` record created
8. Redirect back to `/matches` for next comparison or updated ranking

### Ranking Calculation Flow

1. User makes sufficient comparisons for a term
2. `rank_courses_binary_search()` is called with courses and comparisons for that term
3. Binary search insertion creates sorted list
4. `calculate_course_scores()` converts ranks to 0-10 scores (internal use)
5. Rankings stored in `UserCoursePreference.ranking_position` (1-based for display)
6. Template displays courses sorted by ranking_position, then by status (starred before hearted)

## Security Considerations

1. **Password Hashing**: Werkzeug's `generate_password_hash()` uses SHA-256 with salt - passwords are never stored in plaintext
2. **SQL Injection Prevention**: SQLAlchemy ORM automatically escapes user input in queries
3. **Session Security**: Session IDs are random and stored server-side - only session ID in cookie
4. **Authentication**: `@login_required` decorator protects routes, redirects to login if not authenticated
5. **Input Validation**: Form inputs validated server-side (e.g., checking course IDs exist, actions are valid)

## Performance Considerations

1. **Database Indexing**: Foreign keys automatically indexed by SQLAlchemy
2. **Query Optimization**: Uses SQLAlchemy's `filter()` and `join()` for efficient database queries
3. **Lazy Loading**: Relationships use lazy loading (fetch on access) to avoid N+1 queries
4. **Weighted Selection**: Creating a list with repeated entries for weighted selection is O(n) but acceptable for typical pool sizes (< 1000 courses)
5. **JSON Parsing**: Preferences parsed on every route access - could be cached but overhead is minimal

## Future Extensibility

The architecture supports several potential enhancements:

1. **Additional Terms**: New semester JSON files can be added and parsed automatically
2. **New Requirement Types**: JSON-based Gen Ed system can be extended to other requirement categories
3. **Recommendation Improvements**: Weighted selection algorithm can be refined with machine learning
4. **Multi-User Features**: Database schema supports comparisons between users (not yet implemented)
5. **Export Functionality**: Rankings can be exported as CSV/PDF using existing `ranking_position` field

## Testing Considerations

While not explicitly implemented, the architecture supports testing:

- **Database**: Can use in-memory SQLite for test isolation
- **Routes**: Flask test client can simulate requests
- **Algorithms**: Pure functions (`rank_courses_binary_search`, `classify_level`) are easily unit testable
- **Fixtures**: JSON course data can be used as test fixtures

---

This design document provides a comprehensive technical overview of Class Cupid's implementation. For user-facing documentation, see `README.md`.

