from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class Course(db.Model):
    """Course model populated from JSON"""
    __tablename__ = "courses"

    id = db.Column(db.Integer, primary_key=True)
    course_id = db.Column(db.String(20), nullable=False)
    course_number = db.Column(db.String(50))
    course_title = db.Column(db.String(500))
    instructor_name = db.Column(db.String(200))
    term_description = db.Column(db.String(50))
    department = db.Column(db.String(200))
    start_time = db.Column(db.String(20))
    end_time = db.Column(db.String(20))
    days_of_week = db.Column(db.String(20))
    meetings_display = db.Column(db.Text)
    course_url = db.Column(db.String(500))
    description = db.Column(db.Text)
    quotes_json = db.Column(db.Text)
    class_level_attribute = db.Column(db.String(100))
    class_level_attribute_description = db.Column(db.String(200))
    course_component = db.Column(db.String(100))
    subject_description = db.Column(db.String(200))
    catalog_school_description = db.Column(db.String(200))

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

    __table_args__ = (db.UniqueConstraint("course_id", "term_description", name="unique_course_term"),)

    def _get_days_set(self):
        if not self.days_of_week:
            return set()
        day_map = {
            "M": "M",
            "Monday": "M",
            "T": "T",
            "Tuesday": "T",
            "W": "W",
            "Wednesday": "W",
            "Th": "Th",
            "Thursday": "Th",
            "F": "F",
            "Friday": "F",
            "S": "S",
            "Saturday": "S",
            "Su": "Su",
            "Sunday": "Su",
        }
        days = self.days_of_week.split(",")
        return {day_map.get(d.strip(), d.strip()[0] if d.strip() else "") for d in days if d.strip()}

    def get_days_display(self):
        days_set = self._get_days_set()
        day_order = ["Su", "M", "T", "W", "Th", "F", "S"]
        return "".join([day for day in day_order if day in days_set])

    def has_day(self, day_abbr):
        return day_abbr in self._get_days_set()

    def extract_course_number(self):
        if not self.course_number:
            return None
        parts = self.course_number.strip().split()
        if not parts:
            return None
        last_part = parts[-1]
        if last_part.isdigit():
            return int(last_part)
        digits = "".join(filter(str.isdigit, last_part))
        if digits:
            return int(digits)
        return None

    def classify_level(self):
        if self.course_number and self.course_number.upper().startswith("GENED"):
            return "Alpha"
        if self.class_level_attribute:
            if self.class_level_attribute == "PRIMGRAD":
                return "Grad_low"
            if self.class_level_attribute == "GRADCOURSE":
                return "Grad_research"
        num = self.extract_course_number()
        if num is None:
            if self.course_number:
                parts = self.course_number.split()
                if parts and any(c.isalpha() for c in parts[-1]):
                    return "Alpha"
            return "Unknown"
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
        if 1 <= num <= 99 or 1000 <= num <= 1099:
            return "UG_intro"
        if 100 <= num <= 199 or 1100 <= num <= 1999:
            return "UG_mid"
        if 200 <= num <= 299 or 2000 <= num <= 2999:
            return "Grad_low"
        if 300 <= num <= 399 or 3000 <= num <= 3999:
            return "Grad_research"
        return "Unknown"
