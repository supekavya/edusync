# EduSync — Academic Staff Management System

A web-based platform for managing academic staff in a college environment. Built with Flask and SQLite, EduSync streamlines attendance tracking, leave management, subject allocation, and performance analytics.

---

## Features

### Admin
- **Dashboard** — overview of attendance rates, leave stats, and teacher performance
- **Teacher Management** — add, view, and manage teacher profiles
- **Attendance Tracking** — view and filter attendance records, export to CSV
- **Leave Management** — approve or reject teacher leave requests
- **Subject Allocation** — ML-based subject allocation with conflict detection
- **Feedback & Sentiment** — view student feedback with sentiment analysis
- **Announcements** — post notices visible to all teachers
- **Reports** — performance analytics and department-wise insights

### Teacher
- **Home** — attendance summary, leave balance, and announcements
- **Attendance** — GPS-based check-in with location verification
- **Leave** — apply for leave, track request status
- **Subject Preference** — submit subject preferences for the semester
- **Profile** — view personal details and allocated subject

### Student
- **Feedback** — submit anonymous feedback for teachers

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.11, Flask 3.0 |
| Database | SQLite |
| ML Models | scikit-learn, joblib |
| Sentiment Analysis | TextBlob, NLTK |
| Frontend | Jinja2, HTML/CSS/JS |
| Deployment | Render (gunicorn) |

---

## Running Locally

### 1. Clone or extract the project

```bash
cd edusync-flask
```

### 2. Create a virtual environment

```bash
python -m venv venv
source venv/bin/activate        # Mac/Linux
venv\Scripts\activate           # Windows
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Download NLTK data

```bash
python -c "import nltk; nltk.download('punkt'); nltk.download('averaged_perceptron_tagger')"
```

### 5. Run the app

```bash
python app.py
```

Visit `http://127.0.0.1:5000`

---

## Default Login Credentials

| Role | User ID | Password |
|---|---|---|
| Admin | `admin` | `Admin@123` |
| Teacher | *(teacher ID)* | `Teacher@123` |

> **Important:** Change the admin password immediately after first login.

---

## Deploying to Render

1. Push the project to a GitHub repository
2. Go to [render.com](https://render.com) and create a **New Web Service**
3. Connect your GitHub repo
4. Render will auto-detect `render.yaml` and configure everything
5. Click **Deploy**

The `render.yaml` already sets:
- Python 3.11 runtime
- `pip install` + NLTK data download as the build command
- `gunicorn app:app` as the start command
- Auto-generated `SECRET_KEY`

> **Note:** Render's free tier uses an ephemeral filesystem — the SQLite database resets on each deploy. For persistent data, enable a Render Disk or migrate to PostgreSQL.

---

## Project Structure

```
edusync-flask/
├── app.py                  # App entry point, blueprint registration
├── schema.py               # Database schema and initialization
├── render.yaml             # Render deployment config
├── requirements.txt
├── routes/
│   ├── admin_routes.py
│   ├── teacher_routes.py
│   ├── auth_routes.py
│   ├── student_routes.py
│   └── notification_routes.py
├── services/
│   ├── attendance_service.py
│   ├── leave_service.py
│   ├── allocation_service.py
│   ├── feedback_service.py
│   ├── teacher_service.py
│   ├── notification_service.py
│   ├── auth_service.py
│   └── ai_service.py
├── templates/
│   ├── admin/
│   ├── teacher/
│   └── student/
├── ai_models/
│   ├── performance_model.pkl
│   └── subject_allocation_model.pkl
└── database/
    └── connection.py
```

---

## Notes

- The database (`attendance.db`) is created automatically on first run
- GPS-based attendance requires the teacher to be within the configured radius of the college location
- Subject allocation uses a trained ML model with a rule-based fallback if the model is unavailable
