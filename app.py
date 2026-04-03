import os
import json
import random
import re
import shutil
from pathlib import Path

from flask import Flask, flash, jsonify, redirect, render_template, request, session, url_for
from sqlalchemy import and_, or_
import click

from helpers import (
    apology,
    extract_meeting_fields,
    filter_published_instructor_names,
    parse_clock_to_minutes,
    profile_complete,
)
from models import db, Course


def _database_uri():
    override = os.environ.get("SQLALCHEMY_DATABASE_URI_OVERRIDE")
    if override:
        return override
    root_dir = Path(__file__).resolve().parent
    bundled = root_dir / "catalog.db"
    if os.environ.get("VERCEL"):
        tmp = Path("/tmp") / "classcupid_catalog.db"
        if bundled.is_file() and not tmp.is_file():
            shutil.copy(bundled, tmp)
        return f"sqlite:///{tmp}"
    return f"sqlite:///{root_dir / 'catalog.db'}"


app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = _database_uri()
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-for-production")

db.init_app(app)

MAX_SESSION_PREFS = 400

with app.app_context():
    db.create_all()


class ProfileProxy:
    def __init__(self, data):
        self._d = data or {}

    @property
    def affiliation(self):
        return self._d.get("affiliation")

    @property
    def year(self):
        return self._d.get("year")

    def get_terms(self):
        t = self._d.get("terms")
        if not t:
            return []
        return t if isinstance(t, list) else [t]

    def get_concentrations(self):
        c = self._d.get("concentrations")
        return c or []

    def get_requirements(self):
        r = self._d.get("requirements")
        return r or []

    def get_schools(self):
        s = self._d.get("schools")
        return s or []


class ComparisonRef:
    __slots__ = ("winner_course_id", "loser_course_id")

    def __init__(self, w, l):
        self.winner_course_id = w
        self.loser_course_id = l


class SavedPref:
    def __init__(self, course, status):
        self.course = course
        self.status = status
        self.ranking_position = None


def _course_prefs():
    return session.setdefault("course_prefs", {})


def _swipe_stack():
    return session.setdefault("swipe_stack", [])


def _comparisons_list():
    return session.setdefault("comparisons", [])


def _trim_session_prefs():
    prefs = _course_prefs()
    stack = _swipe_stack()
    while len(prefs) > MAX_SESSION_PREFS and stack:
        oldest = stack.pop(0)
        prefs.pop(str(oldest), None)
    session.modified = True


def _seen_course_ids():
    return [int(k) for k in _course_prefs().keys()]


def _comparisons_as_refs():
    return [ComparisonRef(a[0], a[1]) for a in _comparisons_list()]


@app.context_processor
def inject_globals():
    return dict(profile=session.get("profile"))


@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
def index():
    p = session.get("profile") or {}
    if p.get("affiliation"):
        return redirect(url_for("discover"))
    return redirect(url_for("profile"))


@app.route("/profile", methods=["GET", "POST"])
def profile():
    if request.method == "POST":
        terms = request.form.getlist("terms")
        affiliation = request.form.get("affiliation")
        year = request.form.get("year")
        concentrations = request.form.getlist("concentrations")
        requirements = request.form.getlist("requirements")
        schools = request.form.getlist("schools")
        session["profile"] = {
            "terms": terms,
            "affiliation": affiliation,
            "year": year if affiliation == "Harvard College" else None,
            "concentrations": concentrations if affiliation == "Harvard College" else [],
            "requirements": requirements if affiliation == "Harvard College" else [],
            "schools": schools if affiliation == "Other" else [],
        }
        session.modified = True
        flash("Preferences saved!")
        return redirect(url_for("discover"))
    root = Path(__file__).resolve().parent
    try:
        with open(root / "data/json/harvard_college_concentrations.json", "r") as f:
            harvard_concentrations = json.load(f)
    except OSError:
        harvard_concentrations = []
    try:
        with open(root / "data/json/harvard_schools.json", "r") as f:
            harvard_schools = json.load(f)
    except OSError:
        harvard_schools = []
    user = session.get("profile") or {}
    user_concentrations = user.get("concentrations") or []
    user_requirements = user.get("requirements") or []
    user_schools = user.get("schools") or []
    return render_template(
        "profile.html",
        user=user,
        harvard_concentrations=harvard_concentrations,
        harvard_schools=harvard_schools,
        user_concentrations=user_concentrations,
        user_requirements=user_requirements,
        user_schools=user_schools,
    )


@app.route("/profile/reset_all", methods=["POST"])
def reset_all():
    session.pop("course_prefs", None)
    session.pop("swipe_stack", None)
    session.pop("comparisons", None)
    session.modified = True
    flash("All choices cleared. Start swiping again!")
    return redirect(url_for("discover"))


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
    
    # Reverse the list so best courses are first (the binary search builds worst-first)
    sorted_courses.reverse()
    
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
    if "2027 Spring" in term_preferences:
        geneds_files.append("data/json/2027_Spring_Geneds.json")
    if "2026 Fall" in term_preferences:
        geneds_files.append("data/json/2026_Fall_Geneds.json")
    if "2026 Spring" in term_preferences:
        geneds_files.append("data/json/2026_Spring_Geneds.json")
    if "2025 Fall" in term_preferences:
        geneds_files.append("data/json/2025_Fall_Geneds.json")
    
    try:
        # Load GenEds JSON files and merge results
        for geneds_filename in geneds_files:
            geneds_file_path = os.path.join(os.path.dirname(__file__), geneds_filename)
            with open(geneds_file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                # Remove JSON comments (/* ... */) and handle placeholders for Spring GenEds file
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
        "Electrical Engineering": "Engineering Sciences",
        "Mechanical Engineering": "Engineering Sciences",
    }
    
    # Return mapped value if exists, otherwise return original
    return concentration_to_department.get(concentration, concentration)


def is_fysemr_course(course):
    """
    Check if a course is a First Year Seminar (FYSEMR) course.
    """
    return course.course_number and course.course_number.startswith("FYSEMR")


def _get_filtered_discover_courses(profile, seen_course_ids):
    """
    All courses still available to show the user (same filters as recommendation), before weighting.
    Used for progress and for weighted random pick.
    """
    # Get all eligible courses (filtered but not yet weighted)
    query = Course.query
    if seen_course_ids:
        query = query.filter(~Course.id.in_(seen_course_ids))
    
    # Filter by term preference (required - enforced by profile page)
    user_terms = profile.get_terms()
    query = query.filter(Course.term_description.in_(user_terms))
    
    # Filter by affiliation
    if profile.affiliation == "Harvard College":
        year = profile.year
        concentrations = profile.get_concentrations()
        requirements = profile.get_requirements()
        
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
                return fysemr_courses
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
        return filtered_courses

    elif profile.affiliation == "Other":
        # Use completely different algorithm for Other Affiliation users
        schools = profile.get_schools()
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
        
        if eligible_courses:
            return eligible_courses
        return None

    return None


def recommend_course_weighted(profile, seen_course_ids):
    """Recommend a course using weighted selection based on year and course level."""
    pool = _get_filtered_discover_courses(profile, seen_course_ids)
    if not pool:
        return None
    if profile.affiliation == "Other":
        return random.choice(pool)

    year = profile.year
    year_lower = year.lower() if year else None
    weighted_pool = []
    for course in pool:
        level = course.classify_level()
        weight = 0

        if year_lower == "freshman":
            if is_fysemr_course(course):
                weight = 1
            elif level == "UG_intro":
                weight = 8
            elif level == "UG_mid":
                weight = 2
            elif level == "Alpha":
                weight = 2

        elif year_lower == "sophomore":
            if is_fysemr_course(course):
                weight = 0
            elif level == "UG_intro":
                weight = 5
            elif level == "UG_mid":
                weight = 5
            elif level == "SophomoreTutorial":
                weight = 2
            elif level == "SpecialSeminar":
                weight = 2
            elif level == "ReadingResearch":
                weight = 2
            elif level == "Alpha":
                weight = 2

        elif year_lower == "junior":
            if is_fysemr_course(course):
                weight = 0
            elif level == "UG_intro":
                weight = 2
            elif level == "UG_mid":
                weight = 8
            elif level == "Grad_low":
                weight = 3
            elif level == "JuniorTutorial":
                weight = 2
            elif level == "SpecialSeminar":
                weight = 2
            elif level == "ReadingResearch":
                weight = 2
            elif level == "Alpha":
                weight = 2

        elif year_lower == "senior":
            if is_fysemr_course(course):
                weight = 0
            elif level == "UG_intro":
                weight = 1
            elif level == "UG_mid":
                weight = 7
            elif level == "Grad_low":
                weight = 6
            elif level == "SeniorTutorial":
                weight = 2
            elif level == "SpecialSeminar":
                weight = 2
            elif level == "ReadingResearch":
                weight = 2
            elif level == "Alpha":
                weight = 2

        if weight > 0:
            weighted_pool.extend([course] * weight)

    if weighted_pool:
        return random.choice(weighted_pool)
    return None


def discover_pool_stats(profile):
    """Returns (explored_count, total_in_pool, percent_explored) or (None, None, None)."""
    seen_set = set(_seen_course_ids())
    full = _get_filtered_discover_courses(profile, [])
    if not full:
        return None, None, None
    total = len(full)
    remaining = sum(1 for c in full if c.id not in seen_set)
    explored = max(0, total - remaining)
    pct = min(100, int(round(100 * explored / total))) if total else 0
    return explored, total, pct


def _discover_context(profile):
    """Shared template variables for discover page."""
    saved_matches_count = sum(1 for s in _course_prefs().values() if s in ("heart", "star"))
    ex, tot, pct = discover_pool_stats(profile)
    return {
        "saved_matches_count": saved_matches_count,
        "discover_explored": ex,
        "discover_total": tot,
        "discover_pct": pct,
    }


@app.route("/discover")
@profile_complete
def discover():
    """Tinder-style course discovery page with weighted recommendation algorithm"""
    raw_profile = session.get("profile") or {}
    profile = ProfileProxy(raw_profile)
    if not profile.affiliation:
        flash("Please set your preferences first!")
        return redirect(url_for("profile"))
    user_terms = profile.get_terms()
    if not user_terms:
        flash("Please select at least one term preference first!")
        return redirect(url_for("profile"))
    if profile.affiliation == "Harvard College":
        if not profile.year:
            flash("Please complete your profile preferences first!")
            return redirect(url_for("profile"))
    elif profile.affiliation == "Other":
        if not profile.get_schools():
            flash("Please complete your profile preferences first!")
            return redirect(url_for("profile"))

    show_course_id = request.args.get("show_course", type=int)
    if show_course_id:
        course = Course.query.get(show_course_id)
        if course:
            if user_terms and course.term_description not in user_terms:
                course = None
            if course:
                ctx = _discover_context(profile)
                ctx.update(course=course, is_first_visit=False)
                return render_template("discover.html", **ctx)

    seen_course_ids = _seen_course_ids()
    is_first_visit = len(seen_course_ids) == 0
    course = recommend_course_weighted(profile, seen_course_ids)

    if not course:
        prefs = _course_prefs()
        saved_count = sum(1 for s in prefs.values() if s in ("heart", "star"))
        ctx = _discover_context(profile)
        ctx.update(is_first_visit=False)
        if saved_count > 0:
            ctx.update(
                course=None,
                message="No more relevant courses!",
                prompt_type="matches",
                saved_count=saved_count,
            )
            return render_template("discover.html", **ctx)
        ctx.update(
            course=None,
            message="No more courses match your current preferences!",
            prompt_type="profile",
        )
        return render_template("discover.html", **ctx)

    ctx = _discover_context(profile)
    ctx.update(course=course, is_first_visit=is_first_visit)
    return render_template("discover.html", **ctx)


@app.route("/swipe", methods=["POST"])
@profile_complete
def swipe():
    """Handle course swipe action (heart, star, discard)"""
    course_id = request.form.get("course_id", type=int)
    action = request.form.get("action")
    if not course_id or not action:
        return apology("missing course_id or action", 400)
    if action not in ("heart", "star", "discard"):
        return apology("invalid action", 400)
    prefs = _course_prefs()
    stack = _swipe_stack()
    prefs[str(course_id)] = action
    stack.append(course_id)
    _trim_session_prefs()
    session.modified = True
    return redirect(url_for("discover"))


@app.route("/discover/undo", methods=["POST"])
@profile_complete
def discover_undo():
    """Undo the last swipe action on discover page and return to that course"""
    stack = _swipe_stack()
    prefs = _course_prefs()
    if stack:
        last_id = stack.pop()
        prefs.pop(str(last_id), None)
        session.modified = True
        flash("Last action undone!")
        return redirect(url_for("discover", show_course=last_id))
    return redirect(url_for("discover"))


@app.route("/matches")
@profile_complete
def matches():
    """Matches page with sorting game and saved classes"""
    raw_profile = session.get("profile") or {}
    profile = ProfileProxy(raw_profile)
    user_terms = profile.get_terms()
    prefs = _course_prefs()
    saved_rows = []
    for cid_str, status in prefs.items():
        if status not in ("heart", "star"):
            continue
        c = Course.query.get(int(cid_str))
        if c and (not user_terms or c.term_description in user_terms):
            saved_rows.append(SavedPref(c, status))

    courses_by_term = {}
    for pref in saved_rows:
        term = pref.course.term_description or "Other"
        courses_by_term.setdefault(term, []).append(pref)

    all_comparisons = _comparisons_as_refs()

    course_term_map = {}
    for pref in saved_rows:
        course_term_map[pref.course.id] = pref.course.term_description or "Other"

    comparisons_by_term = {}
    for comp in all_comparisons:
        term1 = course_term_map.get(comp.winner_course_id)
        term2 = course_term_map.get(comp.loser_course_id)
        if term1 and term2 and term1 == term2:
            comparisons_by_term.setdefault(term1, []).append(comp)

    rankings_by_term = {}
    show_ranked_list_by_term = {}
    comparison_count_by_term = {}
    min_comparisons_by_term = {}

    for term, prefs_list in courses_by_term.items():
        term_courses = [pref.course for pref in prefs_list]
        term_comparisons = comparisons_by_term.get(term, [])
        comparison_count_by_term[term] = len(term_comparisons)
        total_courses_in_term = len(term_courses)
        min_comparisons_by_term[term] = (
            max(3, min(10, total_courses_in_term - 1)) if total_courses_in_term > 1 else 0
        )
        show_ranked_list_by_term[term] = comparison_count_by_term[term] >= min_comparisons_by_term[term]
        if term_comparisons:
            rankings_by_term[term] = rank_courses_binary_search(term_courses, term_comparisons)
        else:
            rankings_by_term[term] = {}

    comparison_pair = None
    comparison_term = None
    available_terms = [term for term, plist in courses_by_term.items() if len(plist) >= 2]

    if available_terms:
        compared_pairs_by_term = {}
        for term in available_terms:
            compared_pairs_by_term[term] = set()
            for comp in comparisons_by_term.get(term, []):
                compared_pairs_by_term[term].add((comp.winner_course_id, comp.loser_course_id))
                compared_pairs_by_term[term].add((comp.loser_course_id, comp.winner_course_id))
        available_pairs_by_term = {}
        for term in available_terms:
            term_prefs = courses_by_term[term]
            term_compared = compared_pairs_by_term.get(term, set())
            available_pairs = []
            for i, pref1 in enumerate(term_prefs):
                for pref2 in term_prefs[i + 1 :]:
                    if (pref1.course.id, pref2.course.id) not in term_compared:
                        available_pairs.append((pref1.course, pref2.course))
            if available_pairs:
                available_pairs_by_term[term] = available_pairs
        if available_pairs_by_term:
            comparison_term = random.choice(list(available_pairs_by_term.keys()))
            comparison_pair = random.choice(available_pairs_by_term[comparison_term])
        else:
            comparison_term = random.choice(available_terms)
            term_prefs = courses_by_term[comparison_term]
            comparison_pair = tuple(random.sample([pref.course for pref in term_prefs], 2))

    for term, plist in courses_by_term.items():
        show_ranked = show_ranked_list_by_term.get(term, False)
        term_rankings = rankings_by_term.get(term, {})
        if show_ranked and term_rankings:
            plist.sort(key=lambda p: (term_rankings.get(p.course.id, 999)))
            for pref in plist:
                rank_pos = term_rankings.get(pref.course.id, None)
                pref.ranking_position = rank_pos + 1 if rank_pos is not None else None
        else:
            plist.sort(key=lambda p: (0 if p.status == "star" else 1, p.course.course_number))
            for pref in plist:
                pref.ranking_position = None

        manual = session.get("manual_rank_order", {}).get(term)
        if manual and show_ranked:
            id_to_pref = {p.course.id: p for p in plist}
            ordered = []
            for cid in manual:
                if cid in id_to_pref:
                    ordered.append(id_to_pref[cid])
            placed = {p.course.id for p in ordered}
            for p in plist:
                if p.course.id not in placed:
                    ordered.append(p)
            plist[:] = ordered
            for i, pref in enumerate(plist):
                pref.ranking_position = i + 1

    total_comparison_count = sum(comparison_count_by_term.values())
    total_courses = sum(len(plist) for plist in courses_by_term.values())

    show_scroll_rankings_popup = bool(
        any(show_ranked_list_by_term.values())
        and not session.get("scroll_rankings_hint_dismissed")
    )

    return render_template(
        "matches.html",
        comparison_pair=comparison_pair,
        comparison_term=comparison_term,
        courses_by_term=courses_by_term,
        show_ranked_list_by_term=show_ranked_list_by_term,
        comparison_count_by_term=comparison_count_by_term,
        min_comparisons_by_term=min_comparisons_by_term,
        total_comparison_count=total_comparison_count,
        total_courses=total_courses,
        available_terms=available_terms if available_terms else [],
        show_scroll_rankings_popup=show_scroll_rankings_popup,
    )


CALENDAR_DAY_ORDER = ("M", "T", "W", "Th", "F", "S")
CALENDAR_DAY_LABELS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat")
CALENDAR_NUM_DAYS = len(CALENDAR_DAY_ORDER)

_SUBJ_ABBR = {
    "COMPSCI": "CS",
    "MATH": "MA",
    "APMTH": "AM",
    "STAT": "ST",
    "ECON": "EC",
    "GOV": "GV",
    "HIST": "HI",
    "HUMANITIES": "HU",
    "HUM": "HU",
    "SOCIOL": "SO",
    "CHEM": "CH",
    "PHYSICS": "PH",
    "PSYCH": "PY",
    "BIOLOGY": "BI",
    "NEURO": "NR",
    "LING": "LG",
    "E-PSCI": "ES",
    "EPS": "ES",
    "OEB": "OE",
    "MCB": "MC",
    "GENED": "GN",
    "FYSEMR": "FY",
}


def _calendar_short_label(course):
    cn = (course.course_number or "").strip().split()
    if not cn:
        return "Course"
    subj = cn[0].upper()
    num = cn[-1]
    ab = _SUBJ_ABBR.get(subj)
    if not ab:
        ab = subj[:2] if len(subj) <= 4 else (subj[0] + subj[-1]).upper()
    return f"{ab} {num}".strip()


def _course_is_calendar_scheduled(course):
    st = parse_clock_to_minutes(course.start_time)
    et = parse_clock_to_minutes(course.end_time)
    if st is None or et is None or et <= st:
        return False
    days = course._get_days_set() & set(CALENDAR_DAY_ORDER)
    return bool(days)


def _expand_course_events(course, color_idx):
    st = parse_clock_to_minutes(course.start_time)
    et = parse_clock_to_minutes(course.end_time)
    label = _calendar_short_label(course)
    title = (course.course_title or "")[:120]
    out = []
    for d in CALENDAR_DAY_ORDER:
        if d not in course._get_days_set():
            continue
        day_idx = CALENDAR_DAY_ORDER.index(d)
        out.append(
            {
                "course_id": course.id,
                "day_idx": day_idx,
                "start_min": st,
                "end_min": et,
                "label": label,
                "title": title,
                "color_idx": color_idx % 12,
            }
        )
    return out


def _max_concurrent_during_event(e, day_events):
    """Max number of events overlapping at any minute during e's [start, end)."""
    s, end = e["start_min"], e["end_min"]
    if end <= s:
        return 1
    best = 1
    for t in range(s, end):
        c = sum(1 for o in day_events if o["start_min"] <= t < o["end_min"])
        best = max(best, c)
    return max(best, 1)


def _assign_event_lanes(day_events):
    if not day_events:
        return
    events = sorted(day_events, key=lambda e: (e["start_min"], e["end_min"]))
    lanes_end = []
    for e in events:
        lane = None
        for i, end in enumerate(lanes_end):
            if end <= e["start_min"]:
                lane = i
                lanes_end[i] = e["end_min"]
                break
        if lane is None:
            lane = len(lanes_end)
            lanes_end.append(e["end_min"])
        e["lane"] = lane
    for e in events:
        e["lane_count"] = _max_concurrent_during_event(e, day_events)
        if e["lane_count"] == 1:
            e["lane"] = 0


def _build_calendar_payload(saved_courses, hidden_ids):
    tba = []
    scheduled_courses = []
    color_by_id = {}
    ci = 0
    for c in saved_courses:
        if _course_is_calendar_scheduled(c):
            scheduled_courses.append(c)
            color_by_id[c.id] = ci % 12
            ci += 1
        else:
            tba.append(c)

    raw_events = []
    for c in scheduled_courses:
        if c.id in hidden_ids:
            continue
        raw_events.extend(_expand_course_events(c, color_by_id[c.id]))

    by_day = [[] for _ in range(CALENDAR_NUM_DAYS)]
    for e in raw_events:
        by_day[e["day_idx"]].append(e)

    for d_events in by_day:
        _assign_event_lanes(d_events)

    range_start = 9 * 60
    range_end = 17 * 60
    if raw_events:
        mn = min(ev["start_min"] for ev in raw_events)
        mx = max(ev["end_min"] for ev in raw_events)
        range_start = max(7 * 60, (mn // 60 - 1) * 60)
        range_end = min(22 * 60, ((mx + 59) // 60 + 1) * 60)
        if range_end <= range_start:
            range_end = range_start + 8 * 60

    h_start = range_start // 60
    h_end = (range_end + 59) // 60
    hour_labels = list(range(h_start, h_end + 1))
    if len(hour_labels) < 2:
        hour_labels = [9, 17]
    vis_start = hour_labels[0] * 60
    vis_end = hour_labels[-1] * 60
    span = max(vis_end - vis_start, 60)
    n_calendar_intervals = max(1, len(hour_labels) - 1)
    calendar_axis_height_px = n_calendar_intervals * 56

    positioned_by_day = [[] for _ in range(CALENDAR_NUM_DAYS)]
    gap_pct = 1.0
    for day_idx in range(CALENDAR_NUM_DAYS):
        for e in by_day[day_idx]:
            top = (e["start_min"] - vis_start) / span * 100
            height = (e["end_min"] - e["start_min"]) / span * 100
            lc = max(e["lane_count"], 1)
            lane = e["lane"]
            usable = 100.0 - gap_pct * (lc + 1)
            w = usable / lc
            left = gap_pct + lane * (w + gap_pct)
            positioned_by_day[day_idx].append(
                {
                    "course_id": e["course_id"],
                    "label": e["label"],
                    "title": e["title"],
                    "color_idx": e["color_idx"],
                    "top": round(top, 4),
                    "height": round(max(height, 0.8), 4),
                    "left": round(left, 4),
                    "width": round(w, 4),
                }
            )

    return {
        "tba_courses": tba,
        "scheduled_courses": scheduled_courses,
        "positioned_by_day": positioned_by_day,
        "hour_labels": hour_labels,
        "n_calendar_intervals": n_calendar_intervals,
        "calendar_axis_height_px": calendar_axis_height_px,
        "range_start_min": vis_start,
        "range_end_min": vis_end,
        "hidden_ids": hidden_ids,
        "calendar_day_labels": CALENDAR_DAY_LABELS,
        "n_calendar_days": CALENDAR_NUM_DAYS,
    }


@app.route("/calendar")
@profile_complete
def calendar():
    """One-week schedule from saved (heart/star) courses."""
    raw_profile = session.get("profile") or {}
    profile = ProfileProxy(raw_profile)
    user_terms = profile.get_terms()
    prefs = _course_prefs()
    saved = []
    for cid_str, status in prefs.items():
        if status not in ("heart", "star"):
            continue
        c = Course.query.get(int(cid_str))
        if c and (not user_terms or c.term_description in user_terms):
            saved.append(c)

    hidden_raw = session.get("calendar_hidden_course_ids") or []
    hidden_ids = set()
    for x in hidden_raw:
        try:
            hidden_ids.add(int(x))
        except (TypeError, ValueError):
            pass

    ctx = _build_calendar_payload(saved, hidden_ids)
    ctx["all_scheduled_visible"] = bool(ctx["scheduled_courses"]) and all(
        c.id not in hidden_ids for c in ctx["scheduled_courses"]
    )
    return render_template("calendar.html", **ctx)


def _saved_course_ids_for_calendar():
    prefs = _course_prefs()
    out = set()
    for cid_str, status in prefs.items():
        if status in ("heart", "star"):
            try:
                out.add(int(cid_str))
            except ValueError:
                pass
    return out


@app.route("/calendar/visibility", methods=["POST"])
@profile_complete
def calendar_visibility():
    data = request.get_json(silent=True) or {}
    cid = data.get("course_id")
    visible = data.get("visible", True)
    if cid is None:
        return jsonify({"ok": False, "error": "missing course_id"}), 400
    try:
        cid = int(cid)
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "invalid course_id"}), 400

    if cid not in _saved_course_ids_for_calendar():
        return jsonify({"ok": False, "error": "not a saved course"}), 403

    hidden = [int(x) for x in (session.get("calendar_hidden_course_ids") or [])]
    if visible:
        hidden = [x for x in hidden if x != cid]
    elif cid not in hidden:
        hidden.append(cid)
    session["calendar_hidden_course_ids"] = hidden
    session.modified = True
    return jsonify({"ok": True})


@app.route("/calendar/visibility/batch", methods=["POST"])
@profile_complete
def calendar_visibility_batch():
    data = request.get_json(silent=True) or {}
    course_ids = data.get("course_ids")
    visible = data.get("visible", True)
    if not isinstance(course_ids, list):
        return jsonify({"ok": False, "error": "course_ids must be a list"}), 400
    try:
        ids = {int(x) for x in course_ids}
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "invalid ids"}), 400

    allowed = _saved_course_ids_for_calendar()
    ids = ids & allowed
    if not ids:
        return jsonify({"ok": False, "error": "no valid course ids"}), 400

    hidden = set(int(x) for x in (session.get("calendar_hidden_course_ids") or []))
    if visible:
        hidden -= ids
    else:
        hidden |= ids
    session["calendar_hidden_course_ids"] = list(hidden)
    session.modified = True
    return jsonify({"ok": True})


@app.route("/matches/compare", methods=["POST"])
@profile_complete
def compare():
    """Handle sorting game comparison"""
    winner_id = request.form.get("winner_course_id", type=int)
    loser_id = request.form.get("loser_course_id", type=int)
    if not winner_id or not loser_id:
        return apology("missing course IDs", 400)
    if winner_id == loser_id:
        return apology("courses must be different", 400)
    winner_course = Course.query.get(winner_id)
    loser_course = Course.query.get(loser_id)
    if not winner_course or not loser_course:
        return apology("invalid course IDs", 400)
    if winner_course.term_description != loser_course.term_description:
        flash("You can only compare courses from the same semester.", "error")
        return redirect(url_for("matches"))
    existing_pairs = {(a[0], a[1]) for a in _comparisons_list()}
    if (winner_id, loser_id) not in existing_pairs:
        _comparisons_list().append([winner_id, loser_id])
        session.modified = True
    return redirect(url_for("matches"))


@app.route("/matches/undo", methods=["POST"])
@profile_complete
def undo_comparison():
    """Undo the last comparison"""
    cl = _comparisons_list()
    if cl:
        cl.pop()
        session.modified = True
        flash("Last comparison undone", "success")
    else:
        flash("No comparison to undo", "error")
    return redirect(url_for("matches"))


@app.route("/matches/skip", methods=["POST"])
@profile_complete
def skip_comparison():
    flash("Comparison skipped", "info")
    return redirect(url_for("matches"))


@app.route("/matches/dismiss-scroll-hint", methods=["POST"])
@profile_complete
def dismiss_scroll_rankings_hint():
    session["scroll_rankings_hint_dismissed"] = True
    session.modified = True
    return redirect(url_for("matches"))


@app.route("/matches/reorder", methods=["POST"])
@profile_complete
def reorder_rankings():
    data = request.get_json(silent=True) or {}
    term = data.get("term")
    order = data.get("order")
    if not term or not isinstance(order, list):
        return jsonify({"ok": False, "error": "invalid payload"}), 400
    try:
        ids = [int(x) for x in order]
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "invalid ids"}), 400
    manual = session.setdefault("manual_rank_order", {})
    manual[term] = ids
    session.modified = True
    return jsonify({"ok": True})


@app.route("/matches/update_preference", methods=["POST"])
@profile_complete
def update_preference():
    """Update preference status for a saved course"""
    course_id = request.form.get("course_id", type=int)
    action = request.form.get("action")
    if not course_id or not action:
        return apology("missing course_id or action", 400)
    prefs = _course_prefs()
    key = str(course_id)
    if key not in prefs:
        return apology("course not found", 404)
    if action == "remove":
        prefs.pop(key, None)
        _swipe_stack()[:] = [i for i in _swipe_stack() if i != course_id]
    elif action in ("heart", "star"):
        prefs[key] = action
    else:
        return apology("invalid action", 400)
    session.modified = True
    return redirect(url_for("matches"))



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
        
        instructors = course_data.get("publishedInstructors", [])
        instructor_name = filter_published_instructor_names(instructors)

        mf = extract_meeting_fields(course_data.get("meetings"))
        days_of_week = mf["days_of_week"]
        start_time = mf["start_time"]
        end_time = mf["end_time"]
        meetings_display = mf["meetings_display"]
        
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
            'meetings_display': meetings_display,
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
