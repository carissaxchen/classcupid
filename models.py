from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timezone
import json

db = SQLAlchemy()


class User(db.Model):
    """User model with authentication and preferences"""
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    
    # Profile preferences
    affiliation = db.Column(db.String(50))  # "Harvard College" or "Other"
    year = db.Column(db.String(20))  # Freshman, Sophomore, Junior, Senior
    term_preference = db.Column(db.Text)  # JSON array of terms, e.g., ["2025 Fall", "2026 Spring"]
    concentration_preferences = db.Column(db.Text)  # JSON string or comma-separated
    requirement_preferences = db.Column(db.Text)  # JSON string or comma-separated
    school_preferences = db.Column(db.Text)  # JSON string for "Other" affiliation schools
    
    # Relationships
    course_preferences = db.relationship('UserCoursePreference', backref='user', lazy=True, cascade='all, delete-orphan')
    sort_comparisons = db.relationship('SortComparison', backref='user', lazy=True, cascade='all, delete-orphan')
    
    def get_concentrations(self):
        """Parse concentration preferences from JSON or comma-separated string"""
        if not self.concentration_preferences:
            return []
        try:
            return json.loads(self.concentration_preferences)
        except:
            return [c.strip() for c in self.concentration_preferences.split(',') if c.strip()]
    
    def get_requirements(self):
        """Parse requirement preferences from JSON or comma-separated string"""
        if not self.requirement_preferences:
            return []
        try:
            return json.loads(self.requirement_preferences)
        except:
            return [r.strip() for r in self.requirement_preferences.split(',') if r.strip()]
    
    def get_schools(self):
        """Parse school preferences from JSON or comma-separated string"""
        if not self.school_preferences:
            return []
        try:
            return json.loads(self.school_preferences)
        except:
            return [s.strip() for s in self.school_preferences.split(',') if s.strip()]
    
    def get_terms(self):
        """Parse term preferences from JSON or single string (for backward compatibility)"""
        if not self.term_preference:
            return []
        try:
            # Try to parse as JSON array
            terms = json.loads(self.term_preference)
            if isinstance(terms, list):
                return terms
            # If it's a single string, return as list
            return [terms] if terms else []
        except:
            # Backward compatibility: treat as single string or comma-separated
            if ',' in self.term_preference:
                return [t.strip() for t in self.term_preference.split(',') if t.strip()]
            return [self.term_preference] if self.term_preference else []


class Course(db.Model):
    """Course model populated from JSON"""
    __tablename__ = 'courses'
    
    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.String(20), unique=True, nullable=False)  # from courseID
    course_number = db.Column(db.String(50))  # e.g., "COMPSCI 50"
    course_title = db.Column(db.String(500))
    instructor_name = db.Column(db.String(200))  # First instructor or concatenated
    term_description = db.Column(db.String(50))  # e.g., "2025 Fall"
    department = db.Column(db.String(200))  # catalogSubjectDescription
    start_time = db.Column(db.String(20))  # e.g., "1:30pm"
    end_time = db.Column(db.String(20))  # e.g., "4:15pm"
    days_of_week = db.Column(db.String(20))  # e.g., "MWF" or "TuTh"
    course_url = db.Column(db.String(500))
    description = db.Column(db.Text)  # courseDescription (HTML)
    quotes_json = db.Column(db.Text)  # JSON array of QReports quotes
    class_level_attribute = db.Column(db.String(100))  # classLevelAttribute (e.g., "GRADCOURSE", "PRIMGRAD")
    class_level_attribute_description = db.Column(db.String(200))  # classLevelAttributeDescription
    course_component = db.Column(db.String(100))  # courseComponent (e.g., "Tutorial")
    subject_description = db.Column(db.String(200))  # subjectDescription (e.g., "First Year Seminar")
    catalog_school_description = db.Column(db.String(200))  # catalogSchoolDescription
    
    # Requirement flags (booleans)
    science_and_technology_in_society = db.Column(db.Boolean, default=False)
    aesthetics_and_culture = db.Column(db.Boolean, default=False)
    ethics_and_civics = db.Column(db.Boolean, default=False)
    histories_societies_individuals = db.Column(db.Boolean, default=False)
    arts_and_humanities = db.Column(db.Boolean, default=False)
    social_sciences = db.Column(db.Boolean, default=False)
    science_engineering_applied = db.Column(db.Boolean, default=False)
    quantitative_reasoning = db.Column(db.Boolean, default=False)
    concentration_requirement = db.Column(db.Boolean, default=False)
    language_requirement = db.Column(db.Boolean, default=False)
    
    # Relationships
    user_preferences = db.relationship('UserCoursePreference', backref='course', lazy=True)
    winner_comparisons = db.relationship('SortComparison', foreign_keys='SortComparison.winner_course_id', backref='winner_course', lazy=True)
    loser_comparisons = db.relationship('SortComparison', foreign_keys='SortComparison.loser_course_id', backref='loser_course', lazy=True)
    
    def get_quotes(self):
        """Get quotes as a list"""
        if not self.quotes_json:
            return []
        try:
            return json.loads(self.quotes_json)
        except:
            return []
    
    def get_days_display(self):
        """Convert days_of_week string to display format"""
        if not self.days_of_week:
            return ""
        day_map = {
            'M': 'M', 'Monday': 'M',
            'T': 'T', 'Tuesday': 'T',
            'W': 'W', 'Wednesday': 'W',
            'Th': 'Th', 'Thursday': 'Th',
            'F': 'F', 'Friday': 'F',
            'S': 'S', 'Saturday': 'S',
            'Su': 'Su', 'Sunday': 'Su'
        }
        days = self.days_of_week.split(',')
        return ''.join([day_map.get(d.strip(), d.strip()[0] if d.strip() else '') for d in days if d.strip()])
    
    def has_day(self, day_abbr):
        """Check if course meets on a specific day"""
        days_str = self.get_days_display()
        if not days_str:
            return False
        if day_abbr == 'M':
            # Check for M but not Th (Thursday contains T and H)
            return 'M' in days_str and not days_str.startswith('Th')
        elif day_abbr == 'T':
            # Check for T but not Th
            return 'T' in days_str and 'Th' not in days_str
        else:
            return day_abbr in days_str
    
    def extract_course_number(self):
        """Extract numeric course number from course_number field (e.g., 'COMPSCI 50' -> 50, 'ARABIC A' -> None)"""
        if not self.course_number:
            return None
        
        # Split by space and get the last part (usually the number)
        parts = self.course_number.strip().split()
        if not parts:
            return None
        
        # Get the last part (the course number)
        last_part = parts[-1]
        
        # Check if it's purely numeric (not alpha like "A", "Crr")
        if last_part.isdigit():
            return int(last_part)
        
        # Extract digits from the last part (handles cases like "50A" -> 50)
        digits = ''.join(filter(str.isdigit, last_part))
        if digits:
            return int(digits)
        
        return None
    
    def classify_level(self):
        """Classify course difficulty level based on course numbering system"""
        num = self.extract_course_number()
        if num is None:
            # Check if it's an alpha course (e.g., "Arabic A", "English Crr")
            if self.course_number and any(c.isalpha() for c in self.course_number.split()[-1] if self.course_number.split()):
                return "Alpha"  # Alpha courses can be selected by any year
            return "Unknown"
        
        # Special tutorial categories
        if num in (97, 970):
            return "SophomoreTutorial"
        if num in (98, 980):
            return "JuniorTutorial"
        if num in (99, 990):
            return "SeniorTutorial"
        if num in (96, 960):
            return "SpecialSeminar"
        if num in (91, 910):
            return "ReadingResearch"
        
        # General difficulty groups
        if 1 <= num <= 99  or 1000 <= num <= 1099:
            return "UG_intro"  # Introductory undergrad
        if 100 <= num <= 199 or 1100 <= num <= 1999:
            return "UG_mid"  # Undergrad/grad
        if 200 <= num <= 299 or 2000 <= num <= 2999:
            return "Grad_low"  # Primarily grad
        if 300 <= num <= 399 or 3000 <= num <= 3999:
            return "Grad_research"  # Graduate research
        return "Unknown"


class UserCoursePreference(db.Model):
    """Tracks user interactions with courses (heart, star, discard)"""
    __tablename__ = 'user_course_preferences'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey('courses.id'), nullable=False)
    status = db.Column(db.String(20), nullable=False)  # 'heart', 'star', 'discard'
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    
    # Ensure one preference per user-course pair
    __table_args__ = (db.UniqueConstraint('user_id', 'course_id', name='unique_user_course'),)


class SortComparison(db.Model):
    """Tracks sorting game comparisons"""
    __tablename__ = 'sort_comparisons'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    winner_course_id = db.Column(db.Integer, db.ForeignKey('courses.id'), nullable=False)
    loser_course_id = db.Column(db.Integer, db.ForeignKey('courses.id'), nullable=False)
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    
    # Ensure we don't compare the same pair twice
    __table_args__ = (db.UniqueConstraint('user_id', 'winner_course_id', 'loser_course_id', name='unique_comparison'),)

