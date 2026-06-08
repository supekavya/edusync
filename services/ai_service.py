# services/ai_service.py

import joblib
import pandas as pd
import os

BASE_DIR = os.path.dirname(os.path.dirname(__file__))

performance_model_path = os.path.join(BASE_DIR, "ai_models", "performance_model.pkl")
subject_model_path     = os.path.join(BASE_DIR, "ai_models", "subject_allocation_model.pkl")

performance_model = None
subject_bundle    = None

if os.path.exists(performance_model_path):
    performance_model = joblib.load(performance_model_path)

if os.path.exists(subject_model_path):
    subject_bundle = joblib.load(subject_model_path)


# ==========================================
# PERFORMANCE PREDICTION
# ==========================================

def predict_performance(teacher_info):
    if performance_model is None:
        return "Model Not Available"

    input_data = pd.DataFrame({
        "attendance_percentage": [teacher_info["attendance_percentage"]],
        "experience_years":      [teacher_info["experience_years"]],
        "student_rating":        [teacher_info["student_rating"]],
        "workload_hours":        [teacher_info["workload_hours"]],
        "sentiment_score":       [teacher_info.get("sentiment_score", 0.0)],
    })

    label_map = {0: "Average", 1: "Excellent", 2: "Good"}
    prediction = performance_model.predict(input_data)[0]
    return label_map.get(prediction, "Unknown")


# ==========================================
# SUBJECT ALLOCATION
# ==========================================

def get_subject_recommendations(teacher_info, top_n=3):
    """
    Returns a list of dicts:
      [{"subject": str, "confidence": float, "reason": str}, ...]
    Falls back to rule-based when model unavailable.
    """
    dept = teacher_info.get("department", "")

    if subject_bundle is None:
        return _rule_based_recommendations(teacher_info, top_n)

    model         = subject_bundle["model"]
    dept_enc      = subject_bundle["dept_encoder"]
    subj_enc      = subject_bundle["subject_encoder"]
    dept_subjects = subject_bundle["dept_subjects"]

    if dept not in dept_enc.classes_:
        return _rule_based_recommendations(teacher_info, top_n)

    dept_code = dept_enc.transform([dept])[0]

    inp = pd.DataFrame([{
        "dept_encoded":          dept_code,
        "experience_years":      float(teacher_info.get("experience_years", 5)),
        "attendance_percentage": float(teacher_info.get("attendance_percentage", 90)),
        "student_rating":        float(teacher_info.get("student_rating", 4.0)),
        "workload_hours":        float(teacher_info.get("workload_hours", 18)),
        "sentiment_score":       float(teacher_info.get("sentiment_score", 0.0)),
    }])

    proba = model.predict_proba(inp)[0]

    valid_subjects = [s for s in dept_subjects.get(dept, []) if s in subj_enc.classes_]
    if not valid_subjects:
        return _rule_based_recommendations(teacher_info, top_n)

    scores = {s: float(proba[subj_enc.transform([s])[0]]) for s in valid_subjects}
    ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_n]

    total = sum(p for _, p in ranked) or 1
    results = []
    for rank, (subj, prob) in enumerate(ranked):
        confidence = round((prob / total) * 100, 1)
        results.append({
            "subject":    subj,
            "confidence": confidence,
            "reason":     _build_reason(subj, teacher_info, rank),
        })
    return results


def get_all_subject_allocations(teachers_df):
    """Bulk allocation — top-1 recommendation per teacher."""
    results = []
    for _, row in teachers_df.iterrows():
        recs = get_subject_recommendations(row.to_dict(), top_n=1)
        if recs:
            results.append({
                "teacher_id":      row["teacher_id"],
                "name":            row["name"],
                "department":      row["department"],
                "current_subject": row.get("subject", "-"),
                "recommended":     recs[0]["subject"],
                "confidence":      recs[0]["confidence"],
                "reason":          recs[0]["reason"],
            })
    return results


def get_available_subjects_for_dept(department):
    """Return all subjects the model knows for a given department."""
    if subject_bundle is None:
        return []
    return subject_bundle["dept_subjects"].get(department, [])


# ── Helpers ──────────────────────────────────────────────────────────────────

def _rule_based_recommendations(teacher_info, top_n=3):
    dept = teacher_info.get("department", "")
    exp  = float(teacher_info.get("experience_years", 0))
    rat  = float(teacher_info.get("student_rating",   0))

    FALLBACK = {
        "Computer Science":       ["Data Structures", "Database Systems", "Operating Systems"],
        "Information Technology": ["Web Technologies", "Software Engineering", "Cloud Computing"],
        "Electronics":            ["Digital Electronics", "Microprocessors", "Signal Processing"],
        "Mechanical":             ["Thermodynamics", "Machine Design", "Fluid Mechanics"],
        "Civil":                  ["Structural Engineering", "Surveying", "Transportation Eng."],
        "Mathematics":            ["Linear Algebra", "Probability", "Calculus"],
        "Physics":                ["Electromagnetism", "Optics", "Quantum Mechanics"],
        "Chemistry":              ["Physical Chemistry", "Organic Chemistry", "Analytical Chemistry"],
        "AI & ML":                ["Machine Learning", "Deep Learning", "Computer Vision"],
    }

    subjects = FALLBACK.get(dept, [])[:top_n]
    results  = []
    for rank, subj in enumerate(subjects):
        base_conf = 70 - rank * 15
        conf      = min(95, base_conf + (exp * 1.5) + (rat * 3))
        results.append({"subject": subj, "confidence": round(conf, 1),
                        "reason": _build_reason(subj, teacher_info, rank)})
    return results


def _build_reason(subject, teacher_info, rank):
    exp = float(teacher_info.get("experience_years", 0))
    rat = float(teacher_info.get("student_rating",   0))
    att = float(teacher_info.get("attendance_percentage", 0))

    if rank == 0:
        if exp >= 12:
            return f"Best match — {int(exp)} yrs experience signals strong expertise"
        elif rat >= 4.5:
            return f"Best match — excellent student rating of {rat}/5"
        elif att >= 95:
            return f"Best match — outstanding attendance of {att}%"
        else:
            return "Best overall fit based on profile"
    elif rank == 1:
        return "Strong secondary option based on department profile"
    else:
        return "Suitable alternative with room to develop"