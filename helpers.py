import re
from functools import wraps
from flask import redirect, session, url_for


def profile_complete(f):
    """Require saved preferences (no login)."""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("profile") or not session["profile"].get("affiliation"):
            return redirect(url_for("profile"))
        return f(*args, **kwargs)

    return decorated_function


def apology(message, code=400):
    """Render message as an apology to user."""

    def escape(s):
        for old, new in [
            ("-", "--"),
            (" ", "-"),
            ("_", "__"),
            ("?", "~q"),
            ("%", "~p"),
            ("#", "~h"),
            ("/", "~s"),
            ('"', "''"),
        ]:
            s = s.replace(old, new)
        return s

    return f"Error {code}: {escape(message)}", code


# Phrases that appear in bad Harvard exports where description text is stored as fake instructors
_BAD_INSTRUCTOR_SUBSTRINGS = (
    " course",
    " students",
    " student ",
    "giving",
    "aimed",
    "power of",
    "theoretical computer",
    "introductory",
    "abstraction",
    "computation",
    "algorithm",
    "rigorous proof",
    "mathematical",
    "patrimony",
    "cultural patrimony",
    " should ",
    " where ",
    " ensure ",
    " both ",
    " historical",
    " displayed",
    " studied",
)

# Lines that cannot start a real instructor name (sentence / description fragments)
_BAD_FIRST_WORD = frozenset(
    {
        "and",
        "or",
        "to",
        "the",
        "a",
        "both",
        "for",
        "with",
        "from",
        "in",
        "on",
        "at",
        "by",
        "as",
        "if",
        "when",
        "where",
        "what",
        "how",
        "why",
        "which",
        "who",
        "whose",
        "should",
        "could",
        "would",
        "does",
        "did",
        "will",
        "displayed",
        "studied",
        "ensuring",
    }
)

# Isolated tokens that are English words, not surnames (catalog often splits description into one word per row)
_NON_NAME_SINGLE_WORDS = frozenset(
    {
        "displayed",
        "studied",
        "ensuring",
        "historical",
        "returned",
        "taught",
        "offered",
        "required",
        "listed",
        "shown",
        "given",
        "held",
        "called",
        "known",
        "seen",
        "used",
        "made",
        "based",
    }
)


def _is_plausible_instructor_line(raw: str) -> bool:
    """Heuristic: reject description fragments mis-tagged as instructorName."""
    t = raw.strip()
    if not t or len(t) > 55:
        return False
    words = t.split()
    if len(words) > 4:
        return False
    lower = t.lower()
    if any(bad in lower for bad in _BAD_INSTRUCTOR_SUBSTRINGS):
        return False
    if "?" in t or "!" in t:
        return False

    first = words[0].lower()
    if first in _BAD_FIRST_WORD:
        return False

    if len(words) == 1 and first in _NON_NAME_SINGLE_WORDS:
        return False

    # Single token in all lowercase is almost never a faculty name in this export
    if len(words) == 1 and t == t.lower() and len(t) > 2:
        return False

    # Remaining words look like a sentence fragment (verbs / glue words)
    if len(words) >= 2:
        rest = [w.lower().strip(".,;:") for w in words[1:]]
        if all(
            w
            in (
                "studied",
                "displayed",
                "stored",
                "returned",
                "held",
                "given",
                "listed",
                "shown",
                "historical",
                "cultural",
                "both",
                "ensure",
                "ensuring",
            )
            for w in rest
        ):
            return False

    return True


def filter_published_instructor_names(instructors):
    """
    Join instructor names from publishedInstructors, dropping entries that are
    clearly not person names (data-quality issues in some catalog exports).
    """
    if not instructors:
        return None
    names = []
    for inst in instructors:
        if not isinstance(inst, dict):
            continue
        raw = (inst.get("instructorName") or "").strip()
        if not raw:
            continue
        if not _is_plausible_instructor_line(raw):
            continue
        names.append(raw)
    if not names:
        return None
    return ", ".join(names)


def _expand_day_code_block(block: str):
    """
    Expand Harvard compact day codes to UI abbreviations (M, T, W, Th, F, S, Su).
    Examples: MW -> Mon+Wed; TR -> Tue+Thu (T + R); R -> Thu; MTWRF -> weekdays.
    """
    block = block.strip()
    if not block:
        return []
    out = []
    i = 0
    b = block
    while i < len(b):
        two = b[i : i + 2]
        if len(two) == 2 and two.lower() == "th":
            out.append("Th")
            i += 2
            continue
        if len(two) == 2 and two.lower() == "su":
            out.append("Su")
            i += 2
            continue
        c = b[i]
        if c.upper() == "M":
            out.append("M")
        elif c.upper() == "T":
            out.append("T")
        elif c.upper() == "W":
            out.append("W")
        elif c.upper() == "R":
            out.append("Th")
        elif c.upper() == "F":
            out.append("F")
        elif c.upper() == "S":
            out.append("S")
        else:
            pass
        i += 1
    return out


def _format_time_token(digits: str, am_pm: str) -> str:
    """Normalize '0945', '1200' + AM/PM to '9:45am' style (matches older catalog display)."""
    d = digits.strip()
    am_pm = am_pm.strip().upper()
    if len(d) == 4:
        h, m = int(d[:2]), int(d[2:])
    elif len(d) == 3:
        h, m = int(d[0]), int(d[1:])
    elif len(d) in (1, 2):
        h, m = int(d), 0
    else:
        h, m = 12, 0
    suf = "am" if am_pm == "AM" else "pm"
    return f"{h}:{m:02d}{suf}"


def parse_meetings_string(meetings: str):
    """
    Parse strings like 'MW 1200 PM - 0115 PM' or 'TR 0945 AM - 1100 AM'.
    Returns (days_of_week_csv, start_time, end_time, meetings_display).
    If parsing fails, still returns meetings_display for the Time row fallback.
    """
    s = (meetings or "").strip()
    if not s:
        return None, None, None, None
    if re.match(r"^tba$", s, re.I):
        return None, None, None, s

    m = re.match(
        r"^([A-Za-z]+)\s+(\d{1,4})\s*(AM|PM)\s*-\s*(\d{1,4})\s*(AM|PM)\s*$",
        s,
        re.I,
    )
    if not m:
        return None, None, None, s

    day_block, t1, ap1, t2, ap2 = m.groups()
    days = _expand_day_code_block(day_block)
    if not days:
        return None, None, None, s

    days_csv = ",".join(days)
    start_time = _format_time_token(t1, ap1)
    end_time = _format_time_token(t2, ap2)
    return days_csv, start_time, end_time, s


def extract_meeting_fields(meetings):
    """
    Unified extraction for import: meetings may be a string (new exports) or
    list of dicts (older exports with daysOfWeek / startTime / endTime).
    Returns dict: days_of_week, start_time, end_time, meetings_display.
    """
    if meetings is None:
        return {
            "days_of_week": None,
            "start_time": None,
            "end_time": None,
            "meetings_display": None,
        }

    if isinstance(meetings, str):
        d, st, et, md = parse_meetings_string(meetings)
        return {
            "days_of_week": d,
            "start_time": st,
            "end_time": et,
            "meetings_display": md,
        }

    if isinstance(meetings, list) and len(meetings) > 0:
        meeting = meetings[0]
        if isinstance(meeting, dict):
            start_time = meeting.get("startTime")
            end_time = meeting.get("endTime")
            days_list = meeting.get("daysOfWeek") or []
            day_map = {
                "Monday": "M",
                "Tuesday": "T",
                "Wednesday": "W",
                "Thursday": "Th",
                "Friday": "F",
                "Saturday": "S",
                "Sunday": "Su",
            }
            days_of_week = (
                ",".join([day_map.get(day, day) for day in days_list])
                if days_list
                else None
            )
            return {
                "days_of_week": days_of_week,
                "start_time": start_time,
                "end_time": end_time,
                "meetings_display": None,
            }

    return {
        "days_of_week": None,
        "start_time": None,
        "end_time": None,
        "meetings_display": None,
    }
