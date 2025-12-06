# Class Cupid

A Tinder-style course selection web app for Harvard undergrads.

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Initialize the database:
```bash
python app.py
```
This will create the SQLite database file `classcupid.db`.

3. Import course data:
```bash
flask import-courses 2025_Fall_courses.json
```

4. Run the application:
```bash
flask run
```

Or:
```bash
python app.py
```

5. Open your browser to `http://localhost:5000`

## Features

- **Discover**: Swipe through courses (heart, star, or discard)
- **Matches**: Compare courses in a sorting game and manage saved classes
- **Profile**: Set your year, concentration interests, and requirements

## Database

The app uses SQLite with SQLAlchemy. The database file `classcupid.db` will be created automatically.

## Notes

- Make sure to set your profile preferences before using Discover
- Use the reset button on the Profile page to clear all your choices and start fresh
- QReports quotes can be added to courses by updating the `quotes_json` field in the Course model

