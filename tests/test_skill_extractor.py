
from services.skill_extractor import (
    normalize_text,
    extract_skills,
    categorize_skills,
    analyze_resume_skills,
)


def test_normalize_text():
    assert normalize_text("  PYTHON   SQL  ") == "python sql"


def test_extract_known_skills():
    text = "I have experience with Python, SQL, Pandas and Machine Learning."
    skills = extract_skills(text)

    assert "python" in skills
    assert "sql" in skills
    assert "pandas" in skills
    assert "machine learning" in skills


def test_skill_matching_ignores_case():
    skills = extract_skills("PYTHON and machine LEARNING")

    assert "python" in skills
    assert "machine learning" in skills


def test_custom_skills():
    skills = extract_skills(
        "I have experience with Kubernetes.",
        extra_skills=["Kubernetes"],
    )

    assert "kubernetes" in skills


def test_categorize_skills():
    result = categorize_skills(["python", "sql", "pandas"])

    assert "Programming Languages" in result
    assert "Python and Data Tools" in result


def test_analyze_resume_skills():
    result = analyze_resume_skills(
        "Python developer with SQL and machine learning knowledge."
    )

    assert "skills" in result
    assert result["skill_count"] >= 3
    assert "categories" in result
