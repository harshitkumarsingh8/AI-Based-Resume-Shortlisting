
import pytest

from services.jd_analyzer import analyze_job_description


def test_detects_skills_from_job_description():
    result = analyze_job_description(
        "Required Skills:\n"
        "Python, SQL, Machine Learning\n"
        "Responsibilities:\n"
        "Build data pipelines."
    )

    assert {
        "python",
        "sql",
        "machine learning",
    }.issubset(set(result["skills"]))


def test_detects_preferred_section_skills_without_assigning_priority():
    result = analyze_job_description(
        "Nice to have:\n"
        "Docker, AWS\n"
        "Responsibilities:\n"
        "Build applications."
    )

    assert {"docker", "aws"}.issubset(set(result["skills"]))


def test_analyzer_does_not_assign_skill_priorities():
    result = analyze_job_description(
        "Required Skills:\n"
        "Python, SQL, Machine Learning\n\n"
        "Important Skills:\n"
        "Pandas\n\n"
        "Nice to have:\n"
        "Docker, AWS"
    )

    assert result["must_have_skills"] == []
    assert result["important_skills"] == []
    assert result["preferred_skills"] == []


def test_detects_skills_from_all_sections():
    result = analyze_job_description(
        "Required Skills:\n"
        "Python, SQL\n"
        "Nice to have:\n"
        "Docker, AWS\n"
        "Responsibilities:\n"
        "Build machine learning models."
    )

    assert {
        "python",
        "sql",
        "docker",
        "aws",
        "machine learning",
    }.issubset(set(result["skills"]))


def test_inline_headings_do_not_assign_skill_priorities():
    result = analyze_job_description(
        "Required Skills: Python, SQL\n"
        "Nice to have: Docker, AWS\n"
        "Responsibilities: Build applications."
    )

    assert {"python", "sql", "docker", "aws"}.issubset(
        set(result["skills"])
    )
    assert result["must_have_skills"] == []
    assert result["important_skills"] == []
    assert result["preferred_skills"] == []


def test_detects_important_section_skills_without_assigning_priority():
    result = analyze_job_description(
        "Required Skills:\n"
        "Python\n"
        "Important Skills:\n"
        "SQL, Pandas\n"
        "Nice to have:\n"
        "Docker"
    )

    assert {"python", "sql", "pandas", "docker"}.issubset(
        set(result["skills"])
    )
    assert result["must_have_skills"] == []
    assert result["important_skills"] == []
    assert result["preferred_skills"] == []


def test_extracts_minimum_experience():
    result = analyze_job_description(
        "Python developer with 2 years of experience."
    )

    assert result["minimum_experience_years"] == 2.0


def test_extracts_decimal_experience():
    result = analyze_job_description(
        "Candidates must have at least 1.5 years of experience."
    )

    assert result["minimum_experience_years"] == 1.5


def test_extracts_plus_years_experience():
    result = analyze_job_description(
        "Candidates should have 3+ years of experience."
    )

    assert result["minimum_experience_years"] == 3.0


def test_empty_job_description_raises_value_error():
    with pytest.raises(ValueError, match="cannot be empty"):
        analyze_job_description("   ")


def test_non_string_description_raises_type_error():
    with pytest.raises(TypeError, match="must be a string"):
        analyze_job_description(None)


@pytest.mark.parametrize("value", [123, [], {}, None])
def test_non_string_inputs_raise_type_error(value):
    with pytest.raises(TypeError, match="must be a string"):
        analyze_job_description(value)


def test_returns_skill_count():
    result = analyze_job_description(
        "Python, SQL and Docker experience required."
    )

    assert result["skill_count"] == len(result["skills"])


def test_returns_expected_result_fields():
    result = analyze_job_description(
        "Python developer with 2 years of experience."
    )

    expected_fields = {
        "job_description",
        "skills",
        "skill_count",
        "must_have_skills",
        "important_skills",
        "preferred_skills",
        "skill_alternatives",
        "minimum_experience_years",
        "education_keywords",
        "method",
        "limitation",
    }

    assert expected_fields.issubset(result.keys())


def test_detects_education_keywords():
    result = analyze_job_description(
        "BCA or bachelor's degree in Computer Science."
    )

    assert "bca" in result["education_keywords"]
    assert "computer science" in result["education_keywords"]


def test_empty_description_does_not_create_skills():
    result = analyze_job_description("A candidate will join the team.")

    assert result["skills"] == []
    assert result["skill_count"] == 0
