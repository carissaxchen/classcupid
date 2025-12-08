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
- **Data Files** (`data/`): Organized storage for JSON course catalogs, Gen Ed mappings, and reference data

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

**Design Decision**: Using `Text` columns instead of `CHAR` allows storage of strings of arbitrary length, as users may select many concentrations or requirements. The `_parse_json()` helper method in the User model centralizes JSON parsing logic and returns empty lists for invalid JSON (ensuring robustness for new app rollouts).

#### 2. `courses` Table

Stores course information from Harvard's course catalog JSON:

- **Primary Key**: `id` (Integer, auto-increment)
- **Composite Unique Constraint**: `(course_id, term_description)` - allows the same course to exist across multiple semesters
- **Course Identification**: `course_id` (from catalog), `course_number` (e.g., "COMPSCI 50"), `term_description` (e.g., "2025 Fall")
- **Metadata**: `course_title`, `instructor_name`, `department`, `course_url`, `description`
- **Scheduling**: `start_time`, `end_time`, `days_of_week`
- **Requirement Flags**: Boolean columns for Gen Ed categories, divisional distributions, language requirement, etc.
- **Classification Fields**: `class_level_attribute`, `catalog_school_description`, `course_component`, `catalog_subject`

**Design Decision**: The composite unique constraint on `(course_id, term_description)` enables multi-semester support without duplicating the same course record. This was necessary because during testing, courses like Math 1B and CS50 offered in both Fall and Spring were being overwritten in the database - the Spring version would replace the Fall version when using only `course_id` as unique. Now each semester's offering is stored separately.

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

The database schema uses the following relationships:

```
users (1) ──────< (many) user_course_preferences
  │
  └───────────────< (many) sort_comparisons

courses (1) ──────< (many) user_course_preferences
  │
  ├───────────────< (many) sort_comparisons (as winner_course_id)
  └───────────────< (many) sort_comparisons (as loser_course_id)
```

- **User → UserCoursePreference**: One-to-many with cascade delete (deleting a user removes all preferences)
- **User → SortComparison**: One-to-many with cascade delete
- **Course → UserCoursePreference**: One-to-many
- **Course → SortComparison**: One-to-many (via both `winner_course_id` and `loser_course_id`)

### Why SQLAlchemy?

SQLAlchemy was chosen over raw SQL or SQLite for several reasons:
1. **No Manual SQL Queries**: Writing SQL queries manually would have been very time-consuming
2. **SQL Injection Prevention**: SQLAlchemy automatically escapes dangerous characters, preventing SQL injection attacks
3. **Type Safety**: ORM provides Python-level type checking and validation
4. **Relationship Management**: Automatic handling of foreign keys and relationships simplifies data access

### Course Model Helper Methods

The Course model includes several helper methods for data processing:

- **`extract_course_number()`**: Sanitizes course numbers by extracting digits. Handles variations like:
  - "COMPSCI 50" → 50
  - "MATH 1B" → 1 (extracts digits, ignores letters)
  - "ARABIC A" → None (non-numeric returns None)
  
  This extraction is necessary for the classification algorithm.

- **`get_days_display()`** and **`has_day()`**: Normalize day formats to abbreviated versions (M, T, W, Th, F, S, Su) for consistent display and checking.

- **`classify_level()`**: The most important method for course recommendation - classifies courses into difficulty levels based on Harvard's numbering system (see Algorithm section for details).

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

**Why Weighted Selection?** Initially, the system randomly generated courses from selected requirements/concentrations. However, this caused problems:
- Freshmen were getting high-level classes or tutorials they weren't eligible for
- Upperclassmen were seeing first-year seminars or introductory courses they didn't need

Weighted selection solves this by probabilistically favoring appropriate courses while maintaining discovery and randomness.

**How It Works**: A weight of `n` means the course is added to the selection pool `n` times. For example:
- A course with weight 8 appears 8 times in the pool
- A course with weight 2 appears 2 times in the pool
- Random selection from this weighted pool makes higher-weighted courses 4x more likely to appear

**Weight Assignments by Year**:
- **Freshman**: `UG_intro` (weight 8), `UG_mid` (weight 2), `Alpha` (weight 5), FYSEMR (weight 1)
- **Sophomore**: `UG_intro` (weight 5), `UG_mid` (weight 5), tutorials/seminars/research (weight 2), `Alpha` (weight 5)
- **Junior**: `UG_intro` (weight 2), `UG_mid` (weight 8), `Grad_low` (weight 3), tutorials/seminars/research (weight 2), `Alpha` (weight 5)
- **Senior**: `UG_intro` (weight 1), `UG_mid` (weight 7), `Grad_low` (weight 6), tutorials/seminars/research (weight 2), `Alpha` (weight 5)

**Note**: For graduate students and "Other Affiliation" users, courses are not weighted - all eligible courses appear equally since we don't have detailed information about graduate-level class difficulty.

**Design Decision**: Weighted selection provides probabilistic ranking while maintaining randomness. This prevents deterministic ordering (users won't see courses in the same order every time) while still favoring appropriate courses.

#### Stage 5b: Course Exclusion After Swiping

**How Courses Are Excluded from the Pool**: Once a user swipes a course (heart, star, or discard), it is permanently removed from the recommendation pool until the user resets their choices. This is implemented as follows:

1. **User Action**: When a user swipes on `/discover`, the `/swipe` route creates or updates a `UserCoursePreference` record with `user_id`, `course_id`, and `status` (heart/star/discard).

2. **Collecting Seen Courses**: Before recommending a course, the system queries all `UserCoursePreference` records for the user:
   ```python
   seen_course_ids = [p.course_id for p in UserCoursePreference.query.filter_by(user_id=user.id).all()]
   ```
   This collects all course IDs the user has interacted with, regardless of action type.

3. **Filtering in Recommendation**: The `recommend_course_weighted()` function receives `seen_course_ids` and excludes them from the query:
   ```python
   if seen_course_ids:
       query = query.filter(~Course.id.in_(seen_course_ids))
   ```

4. **Result**: Once swiped, a course won't appear again until the user uses the "Reset All" function (which deletes all `UserCoursePreference` records).

**Design Decision**: Excluding all swiped courses (not just discarded ones) ensures users don't see the same course twice, making the discovery process more efficient.

#### Stage 5c: First Year Seminar and Gen Ed Union Logic

For First Year Seminars and Gen Ed categories, the system uses **union logic** instead of intersection:

- **Example**: If a user selects "First Year Seminar" + "Statistics" concentration, they see:
  - All First Year Seminar courses (regardless of department) **OR**
  - All appropriate Statistics courses
  
- **Reasoning**: Anecdotal evidence suggests users looking for FYSEMRs or Gen Eds are interested in exploring all available options, not just those in their concentration. This union approach provides broader discovery while still filtering by concentration if selected.

**Implementation**: FYSEMR courses are collected in a separate query (`fysemr_query`) and merged with the main filtered results, bypassing concentration and level filtering for FYSEMR courses.

#### Stage 5d: Language Requirement Filtering

The language requirement uses pattern-based identification:

- **Filtering Method**: Identifies introductory language courses by checking:
  1. Course number starts with common language department prefixes (FRENCH, SPANISH, CHINESE, GERMAN, etc.)
  2. Course number pattern matches introductory levels: 1, 2, 3, A, B, AA, BA

- **Reasoning**: Per Harvard catalog guidelines, introductory language classes use alphabetical or low numeric codes. Users fulfilling language requirements are typically beginners, so advanced courses (numbered 100+) are excluded.

- **Known Limitation**: Each department has different language requirement metrics. For example, Chinese requires students to score above 130, meaning some users may need numbered classes like Chinese 120. However, since department-specific requirement information wasn't available in the course catalog JSON, this limitation was accepted. Users needing advanced language courses can find them by selecting specific language concentrations.

#### Stage 6: Other Affiliation Algorithm

For graduate students and other affiliations, completely different filtering applies:

- **School-Specific Filtering**: Uses `filter_courses_for_other_affiliation()` to match `catalog_school_description` to selected schools
- **Special Cases**:
  - Graduate School of Arts and Sciences: Requires `catalog_school_description = "Faculty of Arts & Sciences"` AND course number in ranges 200-299, 300-399, 2000-2999, or 3000-3999 (post-query filtering)
  - Harvard Business School: `catalog_school_description LIKE "%Business School%"`
  - Other schools: Exact string matching
- **No Weighting**: Graduate students see all eligible courses equally (no year-based weighting)

### 2. Binary Search Ranking Algorithm (`rank_courses_binary_search`)

The ranking system uses a binary search insertion sort to create a total ordering from pairwise comparisons. This algorithm was inspired by Beli's algorithm for efficient ranking from sparse comparisons.

#### Algorithm Overview

1. **Comparison Graph Building**: Creates a lookup dictionary mapping course pairs to comparison results:
   - `(course1_id, course2_id) → True` if course1 beats course2
   - Stores both directions for efficient lookup

2. **Win Count Calculation**: Counts direct wins/losses for each course:
   - Each win: +1
   - Each loss: -1
   - Used as fallback ordering when courses haven't been directly compared

3. **Initial Sorting**: Courses are pre-sorted by win count (descending) to provide a good starting order for binary search insertion.

4. **Binary Search Insertion**: For each course in the initial order:
   - Uses binary search to find insertion position in `sorted_courses` list
   - `is_better()` helper determines ordering:
     - **Direct comparison exists**: Returns True/False based on comparison result
     - **Reverse comparison exists**: Negates the reverse comparison
     - **No comparison**: Uses win count difference as proxy
     - **Equal/unknown**: Returns None (defaults to inserting after middle)
   - Binary search logic:
     - If current course > middle course → insert after middle (`low = mid + 1`)
     - If current course < middle course → insert before middle (`high = mid`)
     - If equal/unknown → insert after middle (`low = mid + 1`)
   - Inserts course at calculated position

5. **Reverse and Rank**: The binary search builds the list worst-to-best, so it's reversed to put best courses first. Then 0-based ranks are assigned (0 = best course).

#### Display Logic

**Before Ranking Threshold**: Courses are displayed with:
- Starred courses first
- Hearted courses second
- Sorted by course number within each group

**After Ranking Threshold**: Courses are displayed by their calculated rank (position 1, 2, 3...), with the numerical rank shown in a leftmost column.

#### Minimum Comparisons Formula

The minimum number of comparisons needed before ranking is displayed:
```python
min_comparisons = max(3, min(10, total_courses - 1))
```

**How It Works**:
- `min(10, total_courses - 1)`: Takes the lower value between 10 and (number of courses - 1)
- `max(3, ...)`: Takes the higher value between 3 and the above result
- **Result**: Minimum is always 3, maximum is always 10, scales with course count in between

**Examples**:
- 3 courses: `max(3, min(10, 2))` = `max(3, 2)` = **3 comparisons**
- 5 courses: `max(3, min(10, 4))` = `max(3, 4)` = **4 comparisons**
- 15 courses: `max(3, min(10, 14))` = `max(3, 10)` = **10 comparisons**

#### Key Design Decisions

- **Binary Search Efficiency**: O(n log n) average case vs. O(n²) for naive insertion sort
- **Transitive Inference**: Uses win counts when direct comparison doesn't exist, improving ranking with sparse comparison data
- **Deterministic Ordering**: With sufficient comparisons, produces a consistent ranking
- **Beli's Algorithm Inspiration**: The approach of using binary search for efficient insertion in ranking problems inspired this implementation

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
├── data/
│   ├── images/              # Logo files and icons
│   └── json/                # Course catalogs and reference data
│       ├── 2025_Fall_courses.json
│       ├── 2026_Spring_courses.json
│       ├── 2025_Fall_Geneds.json
│       ├── 2026_Spring_Geneds.json
│       ├── harvard_college_concentrations.json
│       └── harvard_schools.json
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

## Helper Functions (`helpers.py`)

### `login_required()` Decorator

The `login_required()` function is a decorator that protects routes requiring authentication. Decorators add functionality to other functions by wrapping them. When any route is wrapped with `@login_required`, the decorator checks if the user is authenticated by verifying the presence of `session["user_id"]`. If not authenticated, Flask automatically redirects the user to `/login` before the route handler executes.

**Implementation**: Uses Python's `functools.wraps` to preserve the original function's metadata and wraps the route handler in a check for `session.get("user_id")`.

### `apology()` Function

The `apology()` function returns error messages with HTTP status codes. It serves as a centralized error handler that:

1. **Takes Parameters**: Error message string and HTTP status code (defaults to 400)
2. **Escapes Special Characters**: Transforms characters that could break URLs or templates:
   - `-` → `--`
   - Space → `-`
   - `_` → `__`
   - `?` → `~q`
   - `%` → `~p`
   - `#` → `~h`
   - `/` → `~s`
   - `"` → `''`
3. **Returns**: A formatted error message string with the status code

**Design Decision**: Centralized error handling ensures consistent error formatting across the application, though most routes now use Flask's `flash()` messages for better user experience (apology is still used for critical validation errors).

## Route Handlers Overview

While most route handlers are self-explanatory, here are brief descriptions of key routes:

### Authentication Routes

- **`login()`**: Handles user authentication - validates username/password, sets session, redirects to discover page
- **`logout()`**: Clears session and redirects to login page
- **`register()`**: Creates new user account with hashed password, redirects to profile setup

### Core Feature Routes

- **`profile()`**: Displays and handles updates to user preferences (affiliation, year, concentrations, requirements, terms, schools). Loads JSON files for available options and saves user selections as JSON arrays.

- **`reset_all()`**: Allows users to delete all their course preferences and sort comparisons, effectively resetting their account state. Redirects to discover page to start fresh.

- **`discover()`**: Main discovery route that:
  - Checks user has term preference set (redirects to profile if not)
  - Gets list of courses user has already seen
  - Calls `recommend_course_weighted()` to get next course
  - Handles special case: if no courses available, shows context-aware message prompting user to check matches or update profile
  - Supports query parameter `?show_course={id}` for undo functionality

- **`swipe()`**: Handles user interactions on discover page (heart, star, discard). Creates or updates `UserCoursePreference` record and redirects back to discover.

- **`discover_undo()`**: Undoes the last swipe action by deleting the most recent `UserCoursePreference` record and redirecting to the specific course that was undone.

- **`matches()`**: Complex route that:
  - Groups saved courses (hearted/starred) by term
  - Groups comparisons by term (ensuring cross-term comparisons are excluded)
  - Calculates rankings per-term using `rank_courses_binary_search()`
  - Selects random comparison pairs from the same term
  - Determines if rankings should be displayed based on comparison count thresholds
  - Handles display logic: starred first, then hearted, then ranked

- **`compare()`**: Handles comparison game selections. Creates `SortComparison` record for winner/loser pair, ensures courses are from same term, prevents duplicate comparisons via unique constraint.

- **`undo_comparison()`**: Deletes the most recent `SortComparison` record, allowing users to undo their last comparison choice.

- **`skip_comparison()`**: Simply redirects to matches page to show a new comparison pair without recording anything.

- **`update_preference()`**: Allows users to change the status of a saved course (heart/star/remove) from the matches page saved classes list.

### CLI Commands

- **`import_courses(json_file)`**: Flask CLI command to import course data from JSON files. Parses course catalog JSON, extracts all fields, maps to Course model, handles term-specific duplicates via composite unique constraint. Usage: `flask import-courses data/json/2025_Fall_courses.json`

## Security Considerations

### Authentication and Authorization

1. **Password Hashing**: Werkzeug's `generate_password_hash()` uses SHA-256 with salt - passwords are never stored in plaintext. Each password hash is unique even for the same password due to salting.

2. **Session Security**: 
   - Session IDs are randomly generated and stored server-side in filesystem
   - Only the session ID is stored in the client cookie (not sensitive data)
   - Session files stored in `flask_session/` directory

3. **Route Protection**: 
   - `@login_required` decorator protects all routes requiring authentication
   - Automatically redirects unauthenticated users to `/login`
   - User existence is validated in critical routes (handles edge cases like database recreation)

### Input Validation and Injection Prevention

4. **SQL Injection Prevention**: SQLAlchemy ORM automatically escapes user input in all queries. Raw SQL is never used with user input.

5. **Input Validation**: 
   - Form inputs validated server-side (e.g., checking course IDs exist, actions are valid)
   - Type conversion with error handling (e.g., `request.form.get("course_id", type=int)`)
   - Validation checks prevent invalid operations (e.g., comparing a course to itself)


### Data Integrity

6. **Unique Constraints**: Database unique constraints prevent duplicate comparisons, duplicate course-term pairs, and duplicate usernames.

7. **Foreign Key Integrity**: SQLAlchemy enforces referential integrity - cannot delete a user or course that has associated preferences/comparisons without cascade delete.

8. **Error Handling**: Graceful error handling for edge cases (missing user, missing course, invalid actions) with appropriate HTTP status codes and user-friendly error messages.


---

This design document provides a comprehensive technical overview of Class Cupid's implementation. For user-facing documentation, see `README.md`.

