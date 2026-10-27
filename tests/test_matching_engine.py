
import pytest

from services.matching_engine import match_candidate


def test_perfect_skill_match():
    resume = {
        "candidate_name": "Rahul Kumar",
        "filename": "rahul.docx",
        "skills": ["Python", "SQL", "Pandas"],
    }
    job = {
        "skills": ["python", "sql", "pandas"],
        "must_have_skills": ["python", "sql"],
        "important_skills": ["pandas"],
        "preferred_skills": [],
    }

    result = match_candidate(resume, job)

    assert result["match_score"] == 100.0
    assert result["matched_skill_count"] == 3
    assert result["missing_skill_count"] == 0
    assert result["candidate_name"] == "Rahul Kumar"


def test_missing_skills_reduce_score():
    resume = {"skills": ["Python"]}
    job = {
        "skills": ["python", "sql"],
        "must_have_skills": ["python", "sql"],
        "important_skills": [],
        "preferred_skills": [],
    }

    result = match_candidate(resume, job)

    assert result["match_score"] == 50.0
    assert result["matched_skills"] == ["python"]
    assert result["missing_skills"] == ["sql"]


def test_must_have_skills_have_higher_weight():
    resume = {"skills": ["sql"]}
    job = {
        "skills": ["python", "sql"],
        "must_have_skills": ["python"],
        "important_skills": ["sql"],
        "preferred_skills": [],
    }

    result = match_candidate(resume, job)

    # SQL earns 2 points out of 3 + 2 possible points.
    assert result["match_score"] == 40.0


def test_unclassified_skills_are_included():
    resume = {"skills": ["python"]}
    job = {
        "skills": ["python", "docker"],
        "must_have_skills": [],
        "important_skills": [],
        "preferred_skills": [],
    }

    result = match_candidate(resume, job)

    assert result["match_score"] == 50.0
    assert result["missing_skills"] == ["docker"]
    assert "docker" in result["priority_breakdown"]["unclassified"][
        "missing_skills"
    ]


def test_duplicate_priority_assignment_is_not_double_counted():
    resume = {"skills": ["python"]}
    job = {
        "skills": ["python"],
        "must_have_skills": ["python"],
        "important_skills": ["python"],
        "preferred_skills": ["python"],
    }

    result = match_candidate(resume, job)

    assert result["match_score"] == 100.0
    assert result["total_job_skills"] == 1
    assert result["priority_breakdown"]["must_have"]["required_count"] == 1
    assert result["priority_breakdown"]["important"]["required_count"] == 0
    assert result["priority_breakdown"]["preferred"]["required_count"] == 0


def test_empty_job_skills_raise_error():
    with pytest.raises(ValueError, match="no skills"):
        match_candidate(
            {"skills": ["python"]},
            {"skills": []},
        )


def test_missing_skills_field_raises_error():
    with pytest.raises(ValueError, match="must contain 'skills'"):
        match_candidate(
            {"candidate_name": "Rahul"},
            {"skills": ["python"]},
        )


def test_invalid_skills_type_raises_error():
    with pytest.raises(TypeError, match="Skills must be"):
        match_candidate(
            {"skills": "python"},
            {"skills": ["python"]},
        )
