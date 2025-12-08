import os
import json
import random
from datetime import datetime
from flask import Flask, flash, redirect, render_template, request, session, jsonify
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash
from sqlalchemy import func, or_, and_
from sqlalchemy.orm import aliased
import click

from helpers import apology, login_required
from models import db, User, Course, UserCoursePreference, SortComparison

# Configure application
app = Flask(__name__)

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure SQLAlchemy
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///classcupid.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db.init_app(app)


def _run_migrations():
    """Run database migrations to add missing columns to existing databases"""
    from sqlalchemy import text, inspect
    
    try:
        inspector = inspect(db.engine)
        
        # Get existing columns for each table
        table_names = inspector.get_table_names()
        users_columns = {col['name'] for col in inspector.get_columns('users')} if 'users' in table_names else set()
        courses_columns = {col['name'] for col in inspector.get_columns('courses')} if 'courses' in table_names else set()
        
        with db.engine.connect() as conn:
            # Migrations for users table
            if 'affiliation' not in users_columns:
                conn.execute(text("ALTER TABLE users ADD COLUMN affiliation VARCHAR(50)"))
                conn.commit()
            
            if 'term_preference' not in users_columns:
                conn.execute(text("ALTER TABLE users ADD COLUMN term_preference TEXT"))
                conn.commit()
            
            if 'school_preferences' not in users_columns:
                conn.execute(text("ALTER TABLE users ADD COLUMN school_preferences TEXT"))
                conn.commit()
            
            # Migrations for courses table
            if 'class_level_attribute' not in courses_columns:
                conn.execute(text("ALTER TABLE courses ADD COLUMN class_level_attribute VARCHAR(100)"))
                conn.commit()
            
            if 'class_level_attribute_description' not in courses_columns:
                conn.execute(text("ALTER TABLE courses ADD COLUMN class_level_attribute_description VARCHAR(200)"))
                conn.commit()
            
            if 'course_component' not in courses_columns:
                conn.execute(text("ALTER TABLE courses ADD COLUMN course_component VARCHAR(100)"))
                conn.commit()
            
            if 'subject_description' not in courses_columns:
                conn.execute(text("ALTER TABLE courses ADD COLUMN subject_description VARCHAR(200)"))
                conn.commit()
            
            if 'catalog_school_description' not in courses_columns:
                conn.execute(text("ALTER TABLE courses ADD COLUMN catalog_school_description VARCHAR(200)"))
                conn.commit()
    except Exception as e:
        # Silently fail - migrations are optional for new databases
        pass


# Create tables and run migrations
with app.app_context():
    db.create_all()
    # Run migrations to add any missing columns to existing databases
    _run_migrations()


@app.context_processor
def inject_user():
    """Make current user available to all templates"""
    if session.get("user_id"):
        user = User.query.get(session["user_id"])
        return dict(current_user=user)
    return dict(current_user=None)


@app.template_filter('ordinal')
def ordinal_filter(n):
    """Convert number to ordinal string (1st, 2nd, 3rd, etc.)"""
    if n is None:
        return ""
    suffix = ['th', 'st', 'nd', 'rd', 'th'][min(n % 10, 4)]
    if 11 <= (n % 100) <= 13:
        suffix = 'th'
    return f"{n}{suffix}"


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():
    """Redirect to discover page"""
    return redirect("/discover")


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""
    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        
        # Ensure username was submitted
        if not username:
            flash("Please provide a username", "error")
            return render_template("login.html", username=username)
        
        # Ensure password was submitted
        if not password:
            flash("Please provide a password", "error")
            return render_template("login.html", username=username)
        
        # Query database for username
        user = User.query.filter_by(username=username).first()
        
        # Ensure username exists and password is correct
        if not user or not check_password_hash(user.password_hash, password):
            flash("Invalid username and/or password", "error")
            return render_template("login.html", username=username)
        
        # Remember which user has logged in
        session["user_id"] = user.id
        
        # Redirect user to discover page
        return redirect("/discover")
    
    # User reached route via GET (as by clicking a link or via redirect)
    return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""
    # Forget any user_id
    session.clear()
    # Redirect user to login form
    return redirect("/login")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "POST":
        if not request.form.get("username"):
            return apology("must provide username", 400)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 400)

        # Ensure confirmed password was submitted
        elif not request.form.get("confirmation"):
            return apology("must provide password confirmation", 400)

        # Ensure confirmed password matches
        elif request.form.get("password") != request.form.get("confirmation"):
            return apology("passwords must match", 400)

        # Check if username already exists
        if User.query.filter_by(username=request.form.get("username")).first():
            return apology("username is already taken", 400)

        # Create new user
        user = User(
            username=request.form.get("username"),
            password_hash=generate_password_hash(request.form.get("password"))
        )
        db.session.add(user)
        db.session.commit()

        # Set current session to user
        session["user_id"] = user.id

        # Redirect user to profile to set preferences
        return redirect("/profile")

    else:
        return render_template("register.html")


@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    """User profile and preferences"""
    user = User.query.get(session["user_id"])
    
    # Handle case where user doesn't exist (e.g., after database recreation)
    if not user:
        session.clear()
        flash("Your session has expired. Please log in again.", "error")
        return redirect("/login")

    if request.method == "POST":
        # Get form data
        terms = request.form.getlist("terms")
        affiliation = request.form.get("affiliation")
        year = request.form.get("year")
        concentrations = request.form.getlist("concentrations")
        requirements = request.form.getlist("requirements")
        schools = request.form.getlist("schools")
        
        # Update user preferences
        # Store terms as JSON array
        user.term_preference = json.dumps(terms) if terms else None
        user.affiliation = affiliation
        user.year = year if affiliation == "Harvard College" else None
        # Allow 0 concentrations - user can select only requirements
        user.concentration_preferences = json.dumps(concentrations) if affiliation == "Harvard College" else None
        user.requirement_preferences = json.dumps(requirements) if requirements and affiliation == "Harvard College" else None
        user.school_preferences = json.dumps(schools) if schools and affiliation == "Other" else None
        
        db.session.commit()
        flash("Preferences saved!")
        return redirect("/discover")
    
    # GET request - show profile form
    # Load JSON files for options
    try:
        with open('harvard_college_concentrations.json', 'r') as f:
            harvard_concentrations = json.load(f)
    except:
        harvard_concentrations = []
    
    try:
        with open('harvard_schools.json', 'r') as f:
            harvard_schools = json.load(f)
    except:
        harvard_schools = []
    
    # Get user's current preferences
    user_concentrations = user.get_concentrations() if user else []
    user_requirements = user.get_requirements() if user else []
    user_schools = user.get_schools() if user else []
    
    return render_template("profile.html", 
                         user=user,
                         harvard_concentrations=harvard_concentrations,
                         harvard_schools=harvard_schools,
                         user_concentrations=user_concentrations,
                         user_requirements=user_requirements,
                         user_schools=user_schools)


@app.route("/profile/reset_all", methods=["POST"])
@login_required
def reset_all():
    """Reset all user swipes and sorting game data"""
    user_id = session["user_id"]
    
    # Delete all preferences
    UserCoursePreference.query.filter_by(user_id=user_id).delete()
    
    # Delete all comparisons
    SortComparison.query.filter_by(user_id=user_id).delete()
    
    db.session.commit()
    flash("All choices cleared. Start swiping again!")
    return redirect("/discover")


def rank_courses_binary_search(courses, comparisons):
    """
    Rank courses using binary search insertion sort based on comparisons.
    Returns a dictionary mapping course_id to rank (0 = best, higher = worse).
    """
    if not courses:
        return {}
    
    if len(courses) == 1:
        return {courses[0].id: 0}
    
    # Calculate win counts for each course (used as fallback)
    course_wins = {}
    for comp in comparisons:
        course_wins[comp.winner_course_id] = course_wins.get(comp.winner_course_id, 0) + 1
        course_wins[comp.loser_course_id] = course_wins.get(comp.loser_course_id, 0) - 1
    
    # Build comparison lookup: (course1_id, course2_id) -> True if course1 beats course2
    comparison_map = {}
    for comp in comparisons:
        comparison_map[(comp.winner_course_id, comp.loser_course_id)] = True
        comparison_map[(comp.loser_course_id, comp.winner_course_id)] = False
    
    # Helper function to check if course1 is better than course2
    def is_better(course1_id, course2_id):
        # Direct comparison exists
        if (course1_id, course2_id) in comparison_map:
            return comparison_map[(course1_id, course2_id)]
        # Reverse comparison exists
        if (course2_id, course1_id) in comparison_map:
            return not comparison_map[(course2_id, course1_id)]
        # No comparison - use win count difference
        wins1 = course_wins.get(course1_id, 0)
        wins2 = course_wins.get(course2_id, 0)
        if wins1 > wins2:
            return True
        elif wins1 < wins2:
            return False
        # Equal wins - cannot determine
        return None
    
    # Sort courses by win count first (initial ordering)
    course_list = sorted(courses, key=lambda c: course_wins.get(c.id, 0), reverse=True)
    
    # Build sorted list using binary search insertion
    sorted_courses = []
    
    for course in course_list:
        low = 0
        high = len(sorted_courses)
        
        while low < high:
            mid = (low + high) // 2
            mid_course = sorted_courses[mid]
            
            # Check if current course is better than mid course
            better = is_better(course.id, mid_course.id)
            
            if better is True:
                # Current course is better, insert after mid
                low = mid + 1
            elif better is False:
                # Current course is worse, insert before mid
                high = mid
            else:
                # Equal or no comparison - maintain current position (after mid if equal)
                low = mid + 1
        
        sorted_courses.insert(low, course)
    
    # Create rank dictionary (0 = best rank)
    rankings = {}
    for rank, course in enumerate(sorted_courses):
        rankings[course.id] = rank
    
    return rankings


def get_gened_course_codes_for_categories(selected_categories, term_preferences):
    """
    Load GenEds JSON and return a set of course codes (genEdCode) for the selected categories.
    
    Args:
        selected_categories: List of Gen Ed category names (e.g., ["Aesthetics & Culture"])
        term_preferences: List of user's term preferences (e.g., ["2025 Fall", "2026 Spring"])
    
    Returns:
        Set of course codes (e.g., {"GENED 1145", "GENED 1114"})
    """
    gened_course_codes = set()
    
    # Valid Gen Ed categories (must match category names in GenEds JSON)
    valid_gened_categories = {
        "Science & Technology in Society",
        "Aesthetics & Culture",
        "Ethics & Civics",
        "Histories, Societies, Individuals"
    }
    
    # Normalize term_preferences to a list
    if term_preferences is None:
        return set()  # No terms provided, return empty set
    elif isinstance(term_preferences, str):
        term_preferences = [term_preferences]
    elif not isinstance(term_preferences, list):
        return set()  # Invalid input, return empty set
    
    # Determine which GenEds JSON files to use based on term preferences
    geneds_files = []
    if "2026 Spring" in term_preferences:
        geneds_files.append('2026_Spring_Geneds.json')
    if "2025 Fall" in term_preferences:
        geneds_files.append('2025_Fall_Geneds.json')
    
    try:
        # Load GenEds JSON files and merge results
        for geneds_filename in geneds_files:
            geneds_file_path = os.path.join(os.path.dirname(__file__), geneds_filename)
            with open(geneds_file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                # Remove JSON comments (/* ... */) and handle placeholders for Spring GenEds file
                import re
                # Remove single-line and multi-line comments (/* ... */)
                content = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)
                # Remove the "categories" section with placeholders if it exists (not needed for our use case)
                # We only need the "courses" array
                content = re.sub(r',\s*"categories"\s*:\s*\{[^}]*\}', '', content, flags=re.DOTALL)
                geneds_data = json.loads(content)
            
            # Get all courses from the JSON
            courses = geneds_data.get('courses', [])
            
            # For each selected category, find matching courses
            for category in selected_categories:
                if category not in valid_gened_categories:
                    continue
                
                # Find all courses that have this category
                for course in courses:
                    course_categories = course.get('categories', [])
                    if category in course_categories:
                        gened_code = course.get('genEdCode', '')
                        if gened_code:
                            gened_course_codes.add(gened_code)
        
    except Exception as e:
        # If file can't be loaded, return empty set (fall back to flag-based filtering)
        print(f"Error loading GenEds JSON: {e}")
        pass
    
    return gened_course_codes


def filter_courses_for_other_affiliation(query, schools):
    """
    Filter courses for "Other Affiliation" users based on specific school rules.
    
    Args:
        query: SQLAlchemy query object
        schools: List of selected school names from user preferences
    
    Returns:
        Filtered SQLAlchemy query object
    """
    from sqlalchemy import or_
    
    if not schools:
        return query
    
    # Mapping from user-facing school name to catalogSchoolDescription in database
    # Note: GSAS uses "Faculty of Arts & Sciences" with post-query course number filtering
    SCHOOL_TO_CATALOG = {
        "Graduate School of Arts and Sciences": "Faculty of Arts & Sciences",
        "Harvard School of Dental Medicine": "School of Dental Medicine",
        "Harvard T.H. Chan School of Public Health": "Harvard Chan School",
        "Graduate School of Design": "Graduate School of Design",
        "Harvard Divinity School": "Harvard Divinity School",
        "Harvard Graduate School of Education": "Graduate School of Education",
        "Harvard Kennedy School": "Harvard Kennedy School",
        "Harvard Law School": "Harvard Law School",
        "Harvard Medical School": "Harvard Medical School",
    }
    
    school_filters = []
    
    for school in schools:
        if school == "Harvard Business School":
            # Business School uses LIKE query (matches "Business School Doctoral", "Business School MBA", etc.)
            school_filters.append(Course.catalog_school_description.like("%Business School%"))
        elif school in SCHOOL_TO_CATALOG:
            school_filters.append(Course.catalog_school_description == SCHOOL_TO_CATALOG[school])
    
    if school_filters:
        query = query.filter(or_(*school_filters))
    
    return query


def exclude_tutorials(query):
    """
    Helper function to exclude Tutorial courses from a query.
    Filters out courses with component="Tutorial" or "Tutorial" in title.
    """
    query = query.filter(
        or_(
            Course.course_component.is_(None),
            Course.course_component != "Tutorial"
        )
    )
    query = query.filter(
        or_(
            Course.course_title.is_(None),
            ~Course.course_title.ilike("%Tutorial%")
        )
    )
    return query


def map_concentration_to_department(concentration):
    """
    Map concentration name from harvard_college_concentrations.json to 
    catalogSubjectDescription value used in the database.
    
    Some concentrations have different names than their catalogSubjectDescription.
    Returns the department name to use for filtering.
    """
    # Mapping of concentration names to catalogSubjectDescription values
    # Some concentrations have different names than their catalogSubjectDescription
    concentration_to_department = {
        "Applied Math": "Applied Mathematics",
        "Classics": "Classics, The",
        "Comparative Study of Religion": "Religion, The Study of",
        "Germanic Languages and Literature": "Germanic Languages and Literatures",
        "History and Science": "History of Science",
        "Romance Languages and Literature": "Romance Languages and Literatures",
        "Slavic Literatures and Cultures": "Slavic Languages and Literatures",
        "Studies of Women, Gender, and Sexuality": "Women, Gender, and Sexuality, Studies of",
    }
    
    # Return mapped value if exists, otherwise return original
    return concentration_to_department.get(concentration, concentration)


def is_fysemr_course(course):
    """
    Check if a course is a First Year Seminar (FYSEMR) course.
    """
    return course.course_number and course.course_number.startswith("FYSEMR")


def recommend_course_weighted(user, seen_course_ids):
    """
    Recommend a course using weighted selection based on year and course level.
    Returns a single Course object or None.
    """
    # Get all eligible courses (filtered but not yet weighted)
    query = Course.query
    if seen_course_ids:
        query = query.filter(~Course.id.in_(seen_course_ids))
    
    # Filter by term preference (required - enforced by profile page)
    user_terms = user.get_terms()
    query = query.filter(Course.term_description.in_(user_terms))
    
    # Filter by affiliation
    if user.affiliation == "Harvard College":
        year = user.year
        concentrations = user.get_concentrations()
        requirements = user.get_requirements()
        
        # Check if First Year Seminar is selected (needs special handling)
        has_first_year_seminar = requirements and "First Year Seminar" in requirements
        
        # Check if language requirement is selected (needed for later filtering)
        has_language_req = requirements and "Language Requirement" in requirements
        
        # Initialize Gen Ed course codes (will be populated if Gen Ed categories are selected)
        gened_course_codes = set()
        has_gened_codes = False
        
        # Handle First Year Seminar separately - it needs union logic with concentration
        if has_first_year_seminar:
            # Remove "First Year Seminar" from requirements for normal processing
            requirements = [r for r in requirements if r != "First Year Seminar"]
            
            # Create a separate query for First Year Seminar courses (catalogSubject = "FYSEMR")
            # Filter by FYSEMR courses (course_number starts with "FYSEMR")
            fysemr_query = Course.query
            if seen_course_ids:
                fysemr_query = fysemr_query.filter(~Course.id.in_(seen_course_ids))
            
            # Filter by term preference (required - enforced by profile page)
            fysemr_query = fysemr_query.filter(Course.term_description.in_(user_terms))
            
            # Filter for FYSEMR courses (course_number starts with "FYSEMR")
            fysemr_query = fysemr_query.filter(Course.course_number.like("FYSEMR%"))
            
            # Get FYSEMR courses (no concentration or level filtering)
            fysemr_courses = fysemr_query.all()
            
            # If First Year Seminar is the ONLY requirement and no concentrations selected,
            # return ONLY FYSEMR courses (don't run the main query which would return everything)
            if not concentrations and not requirements:
                if not fysemr_courses:
                    return None
                return random.choice(fysemr_courses)
        else:
            fysemr_courses = []
        
        # Build main filter conditions - these will be OR'd together
        # This allows: "Statistics courses OR Aesthetics & Culture Gen Eds OR Arts & Humanities courses"
        main_filter_conditions = []
        
        # Add concentration filter (department)
        # Map concentration names to actual department names in database
        if concentrations:
            mapped_departments = [map_concentration_to_department(conc) for conc in concentrations]
            main_filter_conditions.append(Course.department.in_(mapped_departments))
        
        # Filter by requirements (if selected)
        if requirements:
            req_map = {
                "Science & Technology in Society": Course.science_and_technology_in_society,
                "Aesthetics & Culture": Course.aesthetics_and_culture,
                "Ethics & Civics": Course.ethics_and_civics,
                "Histories, Societies, Individuals": Course.histories_societies_individuals,
                "Arts and Humanities": Course.arts_and_humanities,
                "Social Sciences": Course.social_sciences,
                "Science and Engineering and Applied Science": Course.science_engineering_applied,
                "Quantitative Reasoning": Course.quantitative_reasoning,
                "Language Requirement": Course.language_requirement
            }
            
            # Gen Ed categories that should use specific course codes from GenEds JSON
            gened_categories = {
                "Science & Technology in Society",
                "Aesthetics & Culture",
                "Ethics & Civics",
                "Histories, Societies, Individuals"
            }
            
            # Check which requirements are Gen Ed categories
            selected_gened_categories = [req for req in requirements if req in gened_categories]
            other_requirements = [req for req in requirements if req not in gened_categories]
            
            # If Gen Ed categories are selected, get specific course codes from JSON
            if selected_gened_categories:
                gened_course_codes = get_gened_course_codes_for_categories(selected_gened_categories, user_terms)
                has_gened_codes = len(gened_course_codes) > 0
            
            # Add Gen Ed course codes to main filter conditions
            if gened_course_codes:
                main_filter_conditions.append(Course.course_number.in_(gened_course_codes))
            elif selected_gened_categories:
                # If Gen Ed categories selected but no codes found, use flag-based filtering as fallback
                for req in selected_gened_categories:
                    if req in req_map:
                        main_filter_conditions.append(req_map[req] == True)
            
            # Add other requirements (non-Gen Ed) to main filter conditions
            for req in other_requirements:
                if req in req_map:
                    # Skip language requirement here - handled separately via pattern matching
                    if req != "Language Requirement":
                        main_filter_conditions.append(req_map[req] == True)
        
        # Apply all main filters with OR logic
        # Result: "concentration courses OR Gen Ed courses OR divisional dist courses"
        if main_filter_conditions:
            query = query.filter(or_(*main_filter_conditions))
        
        # Divisional distribution requirements (exclude Tutorials)
        # This must be independent of main_filter_conditions to work correctly
        divisional_requirements = {
            "Arts and Humanities",
            "Social Sciences",
            "Science and Engineering and Applied Science"
        }
        has_divisional_dist = requirements and any(req in divisional_requirements for req in requirements)
        
        # Exclude Tutorial courses when filtering by divisional distribution
        if has_divisional_dist:
            query = exclude_tutorials(query)
        
        # Exclude tutorials for freshmen (they can't take any tutorials)
        # Skip this filtering for Gen Ed courses (they're open to all grades)
        if not has_gened_codes and year == "Freshman":
            query = exclude_tutorials(query)
        # Note: First Year Seminars are handled via weighting (weight=0 for non-freshmen)
        
        # Note: Graduate courses are no longer excluded - they're just weighted smaller
        
        # Get all eligible courses
        # Note: We need all courses for the weighting algorithm to work correctly.
        # Add a safety limit to prevent memory issues with overly broad filters.
        MAX_COURSES = 20000
        eligible_courses = query.limit(MAX_COURSES).all()
        
        if len(eligible_courses) >= MAX_COURSES:
            # If we hit the limit, the filters may be too broad - log a warning
            print(f"Warning: Query returned {MAX_COURSES} courses (limit reached). Consider refining filters.")
        
        # Combine FYSEMR courses with eligible courses (union logic)
        # If First Year Seminar is selected, include FYSEMR courses regardless of concentration
        if has_first_year_seminar:
            # Create a set of course IDs to avoid duplicates
            eligible_course_ids = {course.id for course in eligible_courses}
            for fysemr_course in fysemr_courses:
                if fysemr_course.id not in eligible_course_ids:
                    eligible_courses.append(fysemr_course)
        
        if not eligible_courses:
            return None
        
        # Filter out grade-inappropriate tutorials and reading research
        # Skip all grade-level filtering for Gen Ed courses (they're open to all grades)
        filtered_courses = []
        for course in eligible_courses:
            # Let FYSEMR courses pass through to weighting (handled there via weight=0 for non-freshmen)
            if is_fysemr_course(course):
                filtered_courses.append(course)
                continue
            # Check if this is a Gen Ed course - if so, skip all grade-level filtering
            is_gened_course = has_gened_codes and course.course_number in gened_course_codes
            
            if not is_gened_course:
                level = course.classify_level()
                
                # Rule: Freshmen cannot take SpecialSeminar, ReadingResearch, or any tutorials
                if year == "Freshman" and level in ["ReadingResearch", "SpecialSeminar", "SophomoreTutorial", "JuniorTutorial", "SeniorTutorial"]:
                    continue
                
                # Rule: Freshmen cannot take Grad_low or Grad_research courses
                if year == "Freshman" and level in ["Grad_low", "Grad_research"]:
                    continue
                
                # Rule: Grade-specific tutorials (only appropriate year can take their tutorial)
                if year == "Sophomore" and level in ["JuniorTutorial", "SeniorTutorial"]:
                    continue
                elif year == "Junior" and level in ["SophomoreTutorial", "SeniorTutorial"]:
                    continue
                elif year == "Senior" and level in ["SophomoreTutorial", "JuniorTutorial"]:
                    continue
                
                # Rule: All undergraduates cannot take Grad_research courses
                if level == "Grad_research":
                    continue
                
                # Rule: Exclude any course with "Tutorial" in the title for freshmen
                if year == "Freshman" and course.course_title and "Tutorial" in course.course_title:
                    continue
            
            # Rule: For language requirement, only show introductory language courses (levels 1, 2, 3, A, B)
            if has_language_req:
                # Check if this is a language course (by flag or by course number pattern)
                is_language_course = False
                
                # First check if the course has the language_requirement flag set
                if course.language_requirement:
                    is_language_course = True
                else:
                    # Identify language courses by course number pattern
                    # Language courses typically have course numbers like "FRENCH 1", "SPANISH A", etc.
                    if course.course_number:
                        course_num_upper = course.course_number.upper()
                        # Common language department prefixes
                        language_prefixes = [
                            'FRENCH', 'SPANISH', 'ITALIAN', 'PORTUGUESE', 'GERMAN', 'CHINESE', 'JAPANESE',
                            'KOREAN', 'ARABIC', 'HEBREW', 'RUSSIAN', 'LATIN', 'GREEK', 'SANSKRIT',
                            'SWAHILI', 'YIDDISH', 'VIETNAMESE', 'THAI', 'HINDI', 'URDU', 'TURKISH',
                            'POLISH', 'CZECH', 'UKRAINIAN', 'SWEDISH', 'NORWEGIAN', 'DANISH', 'FINNISH',
                            'DUTCH', 'INDONESIAN', 'TAGALOG', 'AMHARIC', 'BENGALI', 'PERSIAN', 'TAMIL'
                        ]
                        # Check if course number starts with a language prefix
                        for prefix in language_prefixes:
                            if course_num_upper.startswith(prefix):
                                is_language_course = True
                                break
                
                # If it's a language course, filter for introductory levels only
                if is_language_course:
                    course_num = course.extract_course_number()
                    # Check if course number is A or B
                    is_letter_intro = False
                    if course.course_number:
                        parts = course.course_number.strip().split()
                        if parts and len(parts) > 1:
                            last_part = parts[-1].upper()
                            # Check for A, B, AA, BA patterns (introductory letter courses)
                            if last_part in ['A', 'B', 'AA', 'BA']:
                                is_letter_intro = True
                    
                    # Only include courses with course numbers 1, 2, 3, A, B, AA, or BA
                    if not is_letter_intro and (course_num is None or course_num not in [1, 2, 3]):
                        continue
                elif has_language_req:
                    # If language requirement is selected but this isn't a language course, exclude it
                    continue
            
            filtered_courses.append(course)
        
        if not filtered_courses:
            return None
        
        # Weight courses based on year and level
        weighted_pool = []
        year_lower = year.lower() if year else None
        
        for course in filtered_courses:
            # Handle FYSEMR courses: only freshmen get weight, others get 0
            if is_fysemr_course(course):
                if year_lower == "freshman":
                    weighted_pool.extend([course] * 3)  # Weight of 3 for freshmen
                # Non-freshmen get weight 0 (not added to pool)
                continue
            
            level = course.classify_level()
            weight = 0
            
            if year_lower == "freshman":
                if level == "UG_intro":
                    weight = 8  # Heavy on UG_intro (1-99, 1000-1099)
                elif level == "UG_mid":
                    weight = 2  # Moderate weight on UG_mid (100-199, 1100-1999)
                elif level == "Alpha":
                    weight = 4  # Alpha courses available to all
                # NO Grad_low or Grad_research for freshmen
                # NO tutorials, special seminars, or reading research for freshmen
                # First year seminars are handled above (weight=3 for freshmen)
            
            elif year_lower == "sophomore":
                if level == "UG_intro":
                    weight = 5  # Less highly than freshmen, but not too low
                elif level == "UG_mid":
                    weight = 5  # More highly than UG_intro
                elif level == "SophomoreTutorial":  # 97, 970
                    weight = 2
                elif level == "SpecialSeminar":  # 96, 960
                    weight = 2
                elif level == "ReadingResearch":  # 91, 910
                    weight = 2
                elif level == "Alpha":
                    weight = 4  # Same across all years
                # NO Grad_low or Grad_research for sophomores
            
            elif year_lower == "junior":
                if level == "UG_intro":
                    weight = 2  # Very low
                elif level == "UG_mid":
                    weight = 8  # Highly (more than sophomores)
                elif level == "Grad_low":  # 200-299, 2000-2999
                    weight = 3  # Moderately (higher than UG_intro but lower than UG_mid)
                elif level == "JuniorTutorial":  # 98, 980
                    weight = 2
                elif level == "SpecialSeminar":  # 96, 960
                    weight = 2
                elif level == "ReadingResearch":  # 91, 910
                    weight = 2
                elif level == "Alpha":
                    weight = 4  # Same across all years
                # NO Grad_research for juniors
            
            elif year_lower == "senior":
                if level == "UG_intro":
                    weight = 1  # Very low (lowest of all years, practically never display)
                elif level == "UG_mid":
                    weight = 7  # Highly (more than juniors)
                elif level == "Grad_low":  # 200-299, 2000-2999
                    weight = 6  # Highly (more than juniors)
                elif level == "SeniorTutorial":  # 99, 990
                    weight = 2
                elif level == "SpecialSeminar":  # 96, 960
                    weight = 2
                elif level == "ReadingResearch":  # 91, 910
                    weight = 2
                elif level == "Alpha":
                    weight = 4  # Same across all years
                # NO Grad_research for seniors
            
            # Add course to pool with its weight
            if weight > 0:
                weighted_pool.extend([course] * weight)
        
        # Select random course from weighted pool
        if weighted_pool:
            return random.choice(weighted_pool)
        return None
    
    elif user.affiliation == "Other":
        # Use completely different algorithm for Other Affiliation users
        schools = user.get_schools()
        if not schools:
            return None
        
        # Apply school-specific filtering (this filters by catalogSchoolDescription based on selected schools)
        query = filter_courses_for_other_affiliation(query, schools)
        
        # Get all eligible courses after initial filtering (excludes seen courses and filters by school)
        eligible_courses = query.all()
        
        # Post-query filtering for Graduate School of Arts and Sciences (course number ranges)
        if "Graduate School of Arts and Sciences" in schools:
            filtered_courses = []
            for course in eligible_courses:
                # Only filter courses that are from Faculty of Arts & Sciences by course number
                if course.catalog_school_description == "Faculty of Arts & Sciences":
                    course_num = course.extract_course_number()
                    if course_num is not None:
                        # Check if course number is in allowed ranges: 300-399, 3000-3999, 200-299, 2000-2999
                        if ((200 <= course_num <= 299) or 
                            (300 <= course_num <= 399) or
                            (2000 <= course_num <= 2999) or
                            (3000 <= course_num <= 3999)):
                            filtered_courses.append(course)
                    # If course number cannot be extracted, skip FAS courses
                else:
                    # For courses from other selected schools, include them all
                    filtered_courses.append(course)
            eligible_courses = filtered_courses
        
        # Return a random course from the filtered eligible courses
        # This course will be displayed on the discover page
        if eligible_courses:
            return random.choice(eligible_courses)
        return None
    
    return None


@app.route("/discover")
@login_required
def discover():
    """Tinder-style course discovery page with weighted recommendation algorithm"""
    user = User.query.get(session["user_id"])
    
    # Handle case where user doesn't exist (e.g., after database recreation)
    if not user:
        session.clear()
        flash("Your session has expired. Please log in again.", "error")
        return redirect("/login")
    
    # Check if user has set preferences
    if not user.affiliation:
        flash("Please set your preferences first!")
        return redirect("/profile")
    
    # Check if term preference is set
    user_terms = user.get_terms()
    if not user_terms:
        flash("Please select at least one term preference first!")
        return redirect("/profile")
    
    # Check if profile is complete based on affiliation
    if user.affiliation == "Harvard College":
        if not user.year:
            flash("Please complete your profile preferences first!")
            return redirect("/profile")
        # Allow 0 concentrations - user can select divisional distribution only
    elif user.affiliation == "Other":
        if not user.school_preferences:
            flash("Please complete your profile preferences first!")
            return redirect("/profile")
    
    # Check if we should show a specific course (e.g., after undo)
    show_course_id = request.args.get("show_course", type=int)
    if show_course_id:
        course = Course.query.get(show_course_id)
        if course:
            # Verify the course matches user's term preferences
            if user_terms and course.term_description not in user_terms:
                course = None  # Course doesn't match term preference, treat as not found
            if course:
                return render_template("discover.html", course=course)
    
    # Get courses user has already seen
    seen_course_ids = [p.course_id for p in UserCoursePreference.query.filter_by(user_id=user.id).all()]
    
    # Use weighted recommendation algorithm
    course = recommend_course_weighted(user, seen_course_ids)
    
    # If no course found, check if user has saved courses and show appropriate message
    if not course:
        # Check if user has any saved courses (hearts/stars)
        saved_count = UserCoursePreference.query.filter(
            and_(
                UserCoursePreference.user_id == user.id,
                UserCoursePreference.status.in_(['heart', 'star'])
            )
        ).count()
        
        if saved_count > 0:
            # User has saved courses - prompt to go to matches
            return render_template("discover.html", 
                                 course=None, 
                                 message="No more relevant courses!",
                                 prompt_type="matches",
                                 saved_count=saved_count)
        else:
            # No saved courses - prompt to add more subjects
            return render_template("discover.html", 
                                 course=None, 
                                 message="No more courses match your current preferences!",
                                 prompt_type="profile")
    
   
    
    return render_template("discover.html", course=course)


@app.route("/swipe", methods=["POST"])
@login_required
def swipe():
    """Handle course swipe action (heart, star, discard)"""
    user_id = session["user_id"]
    course_id = request.form.get("course_id", type=int)
    action = request.form.get("action")  # 'heart', 'star', 'discard'
    
    if not course_id or not action:
        return apology("missing course_id or action", 400)
    
    if action not in ['heart', 'star', 'discard']:
        return apology("invalid action", 400)
    
    # Check if preference already exists
    preference = UserCoursePreference.query.filter_by(
        user_id=user_id, 
        course_id=course_id
    ).first()
    
    if preference:
        # Update existing preference
        preference.status = action
    else:
        # Create new preference
        preference = UserCoursePreference(
            user_id=user_id,
            course_id=course_id,
            status=action
        )
        db.session.add(preference)
    
    db.session.commit()
    
    # Redirect to next course
    return redirect("/discover")


@app.route("/discover/undo", methods=["POST"])
@login_required
def discover_undo():
    """Undo the last swipe action on discover page and return to that course"""
    user_id = session["user_id"]
    
    # Get the most recent preference for this user
    last_preference = UserCoursePreference.query.filter_by(
        user_id=user_id
    ).order_by(UserCoursePreference.timestamp.desc()).first()
    
    if last_preference:
        # Store the course_id before deleting
        course_id_to_show = last_preference.course_id
        db.session.delete(last_preference)
        db.session.commit()
        flash("Last action undone!")
        # Redirect to discover showing the course that was just undone
        return redirect(f"/discover?show_course={course_id_to_show}")
    
    return redirect("/discover")


@app.route("/matches")
@login_required
def matches():
    """Matches page with sorting game and saved classes"""
    user_id = session["user_id"]
    user = User.query.get(user_id)
    
    # Handle case where user doesn't exist (e.g., after database recreation)
    if not user:
        session.clear()
        flash("Your session has expired. Please log in again.", "error")
        return redirect("/login")
    
    # Get user's liked/starred courses, filtered by term preference
    saved_courses_query = UserCoursePreference.query.filter(
        and_(
            UserCoursePreference.user_id == user_id,
            UserCoursePreference.status.in_(['heart', 'star'])
        )
    ).join(Course)
    
    # Filter by term preference if set
    user_terms = user.get_terms()
    if user_terms:
        saved_courses_query = saved_courses_query.filter(Course.term_description.in_(user_terms))
    
    saved_courses = saved_courses_query.all()
    
    # Group courses by term
    courses_by_term = {}
    for pref in saved_courses:
        term = pref.course.term_description or "Other"
        if term not in courses_by_term:
            courses_by_term[term] = []
        courses_by_term[term].append(pref)
    
    # Get all comparisons and group by term
    all_comparisons = SortComparison.query.filter_by(user_id=user_id).all()
    
    # Build a map of course_id -> term for quick lookup
    course_term_map = {}
    for pref in saved_courses:
        course_term_map[pref.course.id] = pref.course.term_description or "Other"
    
    # Group comparisons by term (both courses must be in same term)
    comparisons_by_term = {}
    for comp in all_comparisons:
        term1 = course_term_map.get(comp.winner_course_id)
        term2 = course_term_map.get(comp.loser_course_id)
        # Only include comparisons where both courses are in the same term
        if term1 and term2 and term1 == term2:
            if term1 not in comparisons_by_term:
                comparisons_by_term[term1] = []
            comparisons_by_term[term1].append(comp)
    
    # Calculate rankings separately for each term
    rankings_by_term = {}
    show_ranked_list_by_term = {}
    comparison_count_by_term = {}
    min_comparisons_by_term = {}
    
    for term, prefs in courses_by_term.items():
        # Get courses for this term
        term_courses = [pref.course for pref in prefs]
        
        # Get comparisons for this term only
        term_comparisons = comparisons_by_term.get(term, [])
        comparison_count_by_term[term] = len(term_comparisons)
        
        # Minimum comparisons needed for this term
        total_courses_in_term = len(term_courses)
        min_comparisons_by_term[term] = max(3, min(10, total_courses_in_term - 1)) if total_courses_in_term > 1 else 0
        show_ranked_list_by_term[term] = comparison_count_by_term[term] >= min_comparisons_by_term[term]
        
        # Calculate rankings for this term only
        if term_comparisons:
            rankings_by_term[term] = rank_courses_binary_search(term_courses, term_comparisons)
        else:
            rankings_by_term[term] = {}
    
    # Select comparison pair - only from the same term
    comparison_pair = None
    comparison_term = None
    
    # Get all available terms with at least 2 courses
    available_terms = [term for term, prefs in courses_by_term.items() if len(prefs) >= 2]
    
    if available_terms:
        # Build compared pairs set (by term)
        compared_pairs_by_term = {}
        for term in available_terms:
            compared_pairs_by_term[term] = set()
            term_comparisons = comparisons_by_term.get(term, [])
            for comp in term_comparisons:
                compared_pairs_by_term[term].add((comp.winner_course_id, comp.loser_course_id))
                compared_pairs_by_term[term].add((comp.loser_course_id, comp.winner_course_id))
        
        # Try to find an available pair within a single term
        available_pairs_by_term = {}
        for term in available_terms:
            term_prefs = courses_by_term[term]
            term_compared = compared_pairs_by_term.get(term, set())
            available_pairs = []
            for i, pref1 in enumerate(term_prefs):
                for pref2 in term_prefs[i+1:]:
                    if (pref1.course.id, pref2.course.id) not in term_compared:
                        available_pairs.append((pref1.course, pref2.course))
            if available_pairs:
                available_pairs_by_term[term] = available_pairs
        
        # Pick a random term with available pairs, or any term if all pairs are compared
        if available_pairs_by_term:
            comparison_term = random.choice(list(available_pairs_by_term.keys()))
            comparison_pair = random.choice(available_pairs_by_term[comparison_term])
        else:
            # All pairs compared in all terms, pick any random pair from same term
            comparison_term = random.choice(available_terms)
            term_prefs = courses_by_term[comparison_term]
            comparison_pair = tuple(random.sample([pref.course for pref in term_prefs], 2))
    
    # Sort each term group based on whether rankings are shown for that term
    for term, prefs in courses_by_term.items():
        show_ranked = show_ranked_list_by_term.get(term, False)
        term_rankings = rankings_by_term.get(term, {})
        
        if show_ranked and term_rankings:
            # Use rankings: sort by rank (lower rank = better = higher in list)
            prefs.sort(key=lambda p: (
                term_rankings.get(p.course.id, 999)  # Use ranking, default to 999 if not ranked
            ))
            # Create ranking positions (1-based)
            for pref in prefs:
                rank_pos = term_rankings.get(pref.course.id, None)
                if rank_pos is not None:
                    pref.ranking_position = rank_pos + 1  # Convert 0-based to 1-based
                else:
                    pref.ranking_position = None
        else:
            # Before ranking: starred courses first, then hearted courses
            prefs.sort(key=lambda p: (0 if p.status == 'star' else 1, p.course.course_number))
            # No ranking positions yet
            for pref in prefs:
                pref.ranking_position = None
    
    # Calculate totals across all terms for progress display
    total_comparison_count = sum(comparison_count_by_term.values())
    total_courses = sum(len(prefs) for prefs in courses_by_term.values())
    
    # Determine if any term has enough comparisons (for general progress message)
    any_ranked = any(show_ranked_list_by_term.values())
    
    return render_template("matches.html",
                         comparison_pair=comparison_pair,
                         comparison_term=comparison_term,
                         courses_by_term=courses_by_term,
                         show_ranked_list_by_term=show_ranked_list_by_term,
                         comparison_count_by_term=comparison_count_by_term,
                         min_comparisons_by_term=min_comparisons_by_term,
                         total_comparison_count=total_comparison_count,
                         total_courses=total_courses,
                         available_terms=available_terms if 'available_terms' in locals() else [])


@app.route("/matches/compare", methods=["POST"])
@login_required
def compare():
    """Handle sorting game comparison"""
    user_id = session["user_id"]
    winner_id = request.form.get("winner_course_id", type=int)
    loser_id = request.form.get("loser_course_id", type=int)
    
    if not winner_id or not loser_id:
        return apology("missing course IDs", 400)
    
    if winner_id == loser_id:
        return apology("courses must be different", 400)
    
    # Verify both courses exist and are from the same term
    winner_course = Course.query.get(winner_id)
    loser_course = Course.query.get(loser_id)
    
    if not winner_course or not loser_course:
        return apology("invalid course IDs", 400)
    
    # Ensure courses are from the same term
    if winner_course.term_description != loser_course.term_description:
        flash("You can only compare courses from the same semester.", "error")
        return redirect("/matches")
    
    # Check if comparison already exists
    existing = SortComparison.query.filter_by(
        user_id=user_id,
        winner_course_id=winner_id,
        loser_course_id=loser_id
    ).first()
    
    if not existing:
        comparison = SortComparison(
            user_id=user_id,
            winner_course_id=winner_id,
            loser_course_id=loser_id
        )
        db.session.add(comparison)
        db.session.commit()
    
    return redirect("/matches")


@app.route("/matches/undo", methods=["POST"])
@login_required
def undo_comparison():
    """Undo the last comparison"""
    user_id = session["user_id"]
    
    # Get the most recent comparison
    last_comparison = SortComparison.query.filter_by(
        user_id=user_id
    ).order_by(SortComparison.timestamp.desc()).first()
    
    if last_comparison:
        db.session.delete(last_comparison)
        db.session.commit()
        flash("Last comparison undone", "success")
    else:
        flash("No comparison to undo", "error")
    
    return redirect("/matches")


@app.route("/matches/skip", methods=["POST"])
@login_required
def skip_comparison():
    """Skip the current comparison pair"""
    # Just redirect to matches to get a new pair
    flash("Comparison skipped", "info")
    return redirect("/matches")


@app.route("/matches/too-tough", methods=["POST"])
@login_required
def too_tough():
    """Mark both courses as too tough to compare"""
    user_id = session["user_id"]
    course1_id = request.form.get("course1_id", type=int)
    course2_id = request.form.get("course2_id", type=int)
    
    if not course1_id or not course2_id:
        return apology("missing course IDs", 400)
    
    # Just skip this comparison (don't record anything)
    flash("Comparison skipped - too tough to decide!", "info")
    return redirect("/matches")


@app.route("/matches/update_preference", methods=["POST"])
@login_required
def update_preference():
    """Update preference status for a saved course"""
    user_id = session["user_id"]
    course_id = request.form.get("course_id", type=int)
    action = request.form.get("action")  # 'heart', 'star', 'remove'
    
    if not course_id or not action:
        return apology("missing course_id or action", 400)
    
    preference = UserCoursePreference.query.filter_by(
        user_id=user_id,
        course_id=course_id
    ).first()
    
    if not preference:
        return apology("course not found", 404)
    
    if action == "remove":
        db.session.delete(preference)
    elif action in ['heart', 'star']:
        preference.status = action
    else:
        return apology("invalid action", 400)
    
    db.session.commit()
    return redirect("/matches")


@app.cli.command("import-courses")
@click.argument("json_file")
def import_courses(json_file):
    """Import courses from JSON file"""
    print(f"Loading courses from {json_file}...")
    
    with open(json_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    courses_data = data.get('courses', [])
    print(f"Found {len(courses_data)} course entries")
    
    imported = 0
    updated = 0
    skipped = 0
    
    for course_data in courses_data:
        course_id = course_data.get('courseID')
        if not course_id:
            skipped += 1
            continue
        
        # Extract term description early so we can use it for duplicate checking
        term_description = course_data.get('termDescription', '')
        
        # Check if course already exists for this specific term (same course can exist in multiple semesters)
        existing = Course.query.filter_by(
            course_id=str(course_id),
            term_description=term_description
        ).first()
        
        # Extract instructor name
        instructors = course_data.get('publishedInstructors', [])
        instructor_name = ', '.join([inst.get('instructorName', '') for inst in instructors]) if instructors else None
        
        # Extract meeting info
        meetings = course_data.get('meetings', [])
        start_time = None
        end_time = None
        days_of_week = None
        
        if isinstance(meetings, list) and len(meetings) > 0:
            meeting = meetings[0]
            if isinstance(meeting, dict):
                start_time = meeting.get('startTime')
                end_time = meeting.get('endTime')
                days_list = meeting.get('daysOfWeek', [])
                if days_list:
                    # Convert day names to abbreviations
                    day_map = {
                        'Monday': 'M',
                        'Tuesday': 'T',
                        'Wednesday': 'W',
                        'Thursday': 'Th',
                        'Friday': 'F',
                        'Saturday': 'S',
                        'Sunday': 'Su'
                    }
                    days_of_week = ','.join([day_map.get(day, day) for day in days_list])
        
        # Extract requirement flags
        divisional_dist = course_data.get('divisionalDistribution')
        quant_reasoning = course_data.get('quantitativeReasoning')
        
        # Map requirements
        science_tech_soc = False
        aesthetics = False
        ethics = False
        histories = False
        arts_hum = False
        social_sci = False
        science_eng = False
        quant_reason = bool(quant_reasoning)
        concentration_req = False
        language_req = False
        
        # Map divisional distribution
        if divisional_dist:
            if 'Arts and Humanities' in divisional_dist:
                arts_hum = True
            if 'Social Sciences' in divisional_dist:
                social_sci = True
            if 'Science' in divisional_dist and 'Engineering' in divisional_dist:
                science_eng = True
        
        # Note: The JSON doesn't seem to have explicit Gen Ed requirement flags
        # You may need to add logic to detect these from other fields
        
        course_dict = {
            'course_id': str(course_id),
            'course_number': course_data.get('courseNumber', ''),
            'course_title': course_data.get('courseTitle', ''),
            'instructor_name': instructor_name,
            'term_description': course_data.get('termDescription', ''),
            'department': course_data.get('catalogSubjectDescription', ''),
            'start_time': start_time,
            'end_time': end_time,
            'days_of_week': days_of_week,
            'course_url': course_data.get('courseURL', ''),
            'description': course_data.get('courseDescription', ''),
            'quotes_json': None,  # QReports data not in JSON, can be added separately
            'class_level_attribute': course_data.get('classLevelAttribute'),
            'class_level_attribute_description': course_data.get('classLevelAttributeDescription'),
            'course_component': course_data.get('courseComponent'),
            'subject_description': course_data.get('subjectDescription'),
            'catalog_school_description': course_data.get('catalogSchoolDescription'),
            'science_and_technology_in_society': science_tech_soc,
            'aesthetics_and_culture': aesthetics,
            'ethics_and_civics': ethics,
            'histories_societies_individuals': histories,
            'arts_and_humanities': arts_hum,
            'social_sciences': social_sci,
            'science_engineering_applied': science_eng,
            'quantitative_reasoning': quant_reason,
            'concentration_requirement': concentration_req,
            'language_requirement': language_req
        }
        
        if existing:
            # Update existing course
            for key, value in course_dict.items():
                setattr(existing, key, value)
            updated += 1
        else:
            # Create new course
            course = Course(**course_dict)
            db.session.add(course)
            imported += 1
    
    db.session.commit()
    print(f"Import complete: {imported} imported, {updated} updated, {skipped} skipped")


if __name__ == "__main__":
    app.run(debug=True)
