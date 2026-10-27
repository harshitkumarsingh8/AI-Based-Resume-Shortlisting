"""Regression tests for services.candidate_ranker."""

import math

import pytest

import services.candidate_ranker as candidate_ranker
from services.candidate_ranker import rank_candidates


# ============================================================
# TEST HELPERS
# ============================================================

def fake_match_candidate(resume, job):
    """Predictable skill-matching result for isolated tests."""
    return {
        "name": resume.get("name", "Unknown"),
        "filename": resume.get("filename", ""),
        "skills": list(resume.get("skills", [])),
        "match_score": resume.get("test_skill_score", 80.0),
    }


def fake_compare_texts(
    resume_text,
    job_description,
    model=None,
):
    """Predictable semantic result for isolated tests."""
    return {
        "semantic_similarity": 0.65,
        "semantic_score": 60.0,
        "model": "test-semantic-model",
        "limitation": None,
    }


@pytest.fixture(autouse=True)
def mock_matching_engine(monkeypatch):
    """Prevent these tests from depending on actual ML models."""
    monkeypatch.setattr(
        candidate_ranker,
        "match_candidate",
        fake_match_candidate,
    )

    monkeypatch.setattr(
        candidate_ranker,
        "compare_texts",
        fake_compare_texts,
    )


# ============================================================
# INPUT VALIDATION
# ============================================================

def test_resume_analyses_must_be_a_list():
    with pytest.raises(
        TypeError,
        match="Resume analyses must be a list",
    ):
        rank_candidates(
            (),
            {"skills": ["Python"]},
        )


def test_job_analysis_must_be_a_dictionary():
    with pytest.raises(
        TypeError,
        match="Job analysis must be a dictionary",
    ):
        rank_candidates(
            [],
            [],
        )


@pytest.mark.parametrize(
    "value",
    [0, 1, None, "true"],
)
def test_use_semantic_must_be_boolean(value):
    with pytest.raises(
        TypeError,
        match="use_semantic must be a boolean",
    ):
        rank_candidates(
            [],
            {},
            use_semantic=value,
        )


@pytest.mark.parametrize(
    "weight",
    [-0.1, 1.1, float("inf"), float("-inf"), float("nan")],
)
def test_invalid_semantic_weights_are_rejected(weight):
    with pytest.raises(ValueError):
        rank_candidates(
            [],
            {},
            semantic_weight=weight,
        )


@pytest.mark.parametrize(
    "weight",
    [True, False, "0.3", None],
)
def test_non_numeric_semantic_weights_are_rejected(weight):
    with pytest.raises(
        TypeError,
        match="Semantic weight must be a number",
    ):
        rank_candidates(
            [],
            {},
            semantic_weight=weight,
        )


def test_semantic_matching_requires_a_job_description():
    with pytest.raises(
        ValueError,
        match="non-empty job description is required",
    ):
        rank_candidates(
            [{"name": "Candidate A"}],
            {},
            use_semantic=True,
            job_description=" ",
        )


def test_empty_resume_list_returns_empty_results():
    assert rank_candidates([], {}) == []


def test_each_resume_analysis_must_be_a_dictionary():
    with pytest.raises(
        TypeError,
        match="Each resume analysis must be a dictionary",
    ):
        rank_candidates(
            ["not a dictionary"],
            {},
        )


# ============================================================
# SKILL-BASED RANKING
# ============================================================

def test_skill_score_is_preserved_when_semantic_is_disabled():
    result = rank_candidates(
        [
            {
                "name": "Candidate A",
                "skills": ["Python", "SQL"],
                "test_skill_score": 82,
            }
        ],
        {"skills": ["Python", "SQL"]},
    )

    candidate = result[0]

    assert candidate["skill_match_score"] == 82.0
    assert candidate["combined_score"] == 82.0
    assert candidate["match_score"] == 82.0
    assert candidate["semantic_score"] is None
    assert candidate["semantic_weight"] == 0.0
    assert candidate["ranking_method"] == "Skill matching baseline"
    assert candidate["rank"] == 1


def test_skill_score_of_zero_is_valid():
    result = rank_candidates(
        [
            {
                "name": "NoMatch",
                "skills": [],
                "test_skill_score": 0,
            }
        ],
        {"skills": ["Python"]},
    )

    assert result[0]["skill_match_score"] == 0.0
    assert result[0]["match_score"] == 0.0


def test_score_of_100_is_valid():
    result = rank_candidates(
        [
            {
                "name": "Perfect",
                "skills": ["Python"],
                "test_skill_score": 100,
            }
        ],
        {"skills": ["Python"]},
    )

    assert result[0]["skill_match_score"] == 100.0
    assert result[0]["match_score"] == 100.0


@pytest.mark.parametrize(
    "invalid_score",
    [
        None,
        "invalid",
        -1,
        101,
        float("inf"),
        float("-inf"),
        float("nan"),
        True,
    ],
)
def test_invalid_skill_scores_are_rejected(invalid_score):
    def invalid_match(resume, job):
        return {
            "name": resume.get("name", "Candidate"),
            "match_score": invalid_score,
        }

    # Override the automatic mock for this test.
    candidate_ranker.match_candidate = invalid_match

    try:
        with pytest.raises(ValueError):
            rank_candidates(
                [{"name": "Candidate"}],
                {},
            )
    finally:
        candidate_ranker.match_candidate = fake_match_candidate


def test_match_candidate_must_return_a_dictionary(monkeypatch):
    monkeypatch.setattr(
        candidate_ranker,
        "match_candidate",
        lambda resume, job: 75.0,
    )

    with pytest.raises(
        TypeError,
        match="must return a dictionary",
    ):
        rank_candidates(
            [{"name": "Candidate"}],
            {},
        )


# ============================================================
# SEMANTIC SCORE BLENDING
# ============================================================

def test_semantic_score_is_blended_correctly():
    result = rank_candidates(
        [
            {
                "name": "Candidate A",
                "skills": ["Python"],
                "text": "Python developer with NLP experience.",
                "test_skill_score": 80,
            }
        ],
        {"skills": ["Python"]},
        use_semantic=True,
        job_description="Looking for a Python developer.",
        semantic_weight=0.25,
    )

    candidate = result[0]

    # 80 * 0.75 + 60 * 0.25 = 75.
    assert candidate["skill_match_score"] == 80.0
    assert candidate["semantic_score"] == 60.0
    assert candidate["semantic_weight"] == 0.25
    assert candidate["combined_score"] == 75.0
    assert candidate["match_score"] == 75.0
    assert candidate["semantic_model"] == "test-semantic-model"
    assert candidate["semantic_similarity"] == 0.65
    assert candidate["semantic_text_warning"] is None


def test_zero_semantic_weight_keeps_skill_score():
    result = rank_candidates(
        [
            {
                "name": "Candidate",
                "text": "Python developer.",
                "test_skill_score": 85,
            }
        ],
        {},
        use_semantic=True,
        job_description="Python engineer.",
        semantic_weight=0.0,
    )

    assert result[0]["combined_score"] == 85.0
    assert result[0]["semantic_score"] == 60.0


def test_full_semantic_weight_uses_semantic_score():
    result = rank_candidates(
        [
            {
                "name": "Candidate",
                "text": "Python developer.",
                "test_skill_score": 20,
            }
        ],
        {},
        use_semantic=True,
        job_description="Python engineer.",
        semantic_weight=1.0,
    )

    assert result[0]["combined_score"] == 60.0


def test_semantic_matching_passes_model_to_comparison(monkeypatch):
    calls = []

    def compare_spy(resume_text, job_description, model=None):
        calls.append(
            (resume_text, job_description, model)
        )

        return {
            "semantic_similarity": 0.9,
            "semantic_score": 90,
            "model": "spy-model",
            "limitation": None,
        }

    monkeypatch.setattr(
        candidate_ranker,
        "compare_texts",
        compare_spy,
    )

    supplied_model = object()

    result = rank_candidates(
        [
            {
                "name": "Candidate",
                "text": "Experienced Python developer.",
                "test_skill_score": 70,
            }
        ],
        {},
        use_semantic=True,
        job_description="Python developer required.",
        semantic_weight=0.3,
        semantic_model=supplied_model,
    )

    assert calls == [
        (
            "Experienced Python developer.",
            "Python developer required.",
            supplied_model,
        )
    ]

    assert result[0]["semantic_model"] == "spy-model"


def test_empty_resume_text_sets_a_warning():
    result = rank_candidates(
        [
            {
                "name": "NoText",
                "skills": ["Python"],
                "test_skill_score": 80,
                "text": " ",
            }
        ],
        {},
        use_semantic=True,
        job_description="Python engineer required.",
    )

    candidate = result[0]

    assert candidate["semantic_text_warning"] is not None
    assert "No non-empty resume text" in (
        candidate["semantic_text_warning"]
    )


def test_semantic_score_outside_range_is_rejected(monkeypatch):
    monkeypatch.setattr(
        candidate_ranker,
        "compare_texts",
        lambda *args, **kwargs: {
            "semantic_score": 150,
            "semantic_similarity": 1.5,
            "model": "test",
            "limitation": None,
        },
    )

    with pytest.raises(
        ValueError,
        match="Semantic score must be between 0 and 100",
    ):
        rank_candidates(
            [
                {
                    "name": "Candidate",
                    "text": "Python developer.",
                }
            ],
            {},
            use_semantic=True,
            job_description="Python engineer.",
        )


def test_semantic_result_must_be_a_dictionary(monkeypatch):
    monkeypatch.setattr(
        candidate_ranker,
        "compare_texts",
        lambda *args, **kwargs: 0.9,
    )

    with pytest.raises(
        TypeError,
        match="compare_texts\\(\\) must return a dictionary",
    ):
        rank_candidates(
            [
                {
                    "name": "Candidate",
                    "text": "Python developer.",
                }
            ],
            {},
            use_semantic=True,
            job_description="Python engineer.",
        )


# ============================================================
# TEXT PRESERVATION AND SOURCE IMMUTABILITY
# ============================================================

def test_resume_details_and_text_are_preserved():
    source = {
        "name": "Candidate A",
        "email": "candidate@example.com",
        "phone": "1234567890",
        "education": ["BCA"],
        "experience": ["Python Intern"],
        "projects": ["Resume Matcher"],
        "certifications": ["Python Certificate"],
        "skills": ["Python", "NLP"],
        "skill_count": 2,
        "skill_evidence": {
            "Python": [{"snippet": "Used Python."}]
        },
        "text": "Used Python for a resume matching project.",
        "test_skill_score": 85,
    }

    result = rank_candidates(
        [source],
        {"skills": ["Python"]},
    )

    candidate = result[0]

    assert candidate["name"] == "Candidate A"
    assert candidate["email"] == "candidate@example.com"
    assert candidate["phone"] == "1234567890"
    assert candidate["education"] == ["BCA"]
    assert candidate["experience"] == ["Python Intern"]
    assert candidate["projects"] == ["Resume Matcher"]
    assert candidate["certifications"] == ["Python Certificate"]
    assert candidate["skills"] == ["Python", "NLP"]
    assert candidate["skill_count"] == 2
    assert candidate["text"] == source["text"]

    # The source candidate's contents must not be modified.
    assert source["skills"] == ["Python", "NLP"]


def test_resume_text_falls_back_to_next_available_key():
    result = rank_candidates(
        [
            {
                "name": "Candidate",
                "text": " ",
                "full_text": "Python and NLP experience.",
                "test_skill_score": 70,
            }
        ],
        {},
        use_semantic=True,
        job_description="Python role.",
    )

    assert result[0]["semantic_text_warning"] is None


def test_resume_extraction_limitation_is_preserved():
    result = rank_candidates(
        [
            {
                "name": "Candidate",
                "text": "Python experience.",
                "limitation": "Scanned PDF extraction may be incomplete.",
                "test_skill_score": 80,
            }
        ],
        {},
    )

    assert result[0]["resume_extraction_limitation"] == (
        "Scanned PDF extraction may be incomplete."
    )


# ============================================================
# ORDERING AND RANKS
# ============================================================

def test_candidates_are_sorted_by_combined_score_descending():
    result = rank_candidates(
        [
            {
                "name": "Low",
                "test_skill_score": 40,
            },
            {
                "name": "High",
                "test_skill_score": 95,
            },
            {
                "name": "Medium",
                "test_skill_score": 70,
            },
        ],
        {},
    )

    assert [item["name"] for item in result] == [
        "High",
        "Medium",
        "Low",
    ]

    assert [item["rank"] for item in result] == [1, 2, 3]


def test_equal_scores_keep_original_input_order():
    result = rank_candidates(
        [
            {
                "name": "First",
                "test_skill_score": 80,
            },
            {
                "name": "Second",
                "test_skill_score": 80,
            },
            {
                "name": "Third",
                "test_skill_score": 80,
            },
        ],
        {},
    )

    assert [item["name"] for item in result] == [
        "First",
        "Second",
        "Third",
    ]

    assert [item["rank"] for item in result] == [1, 2, 3]


# ============================================================
# TEST RUNNER
# ============================================================

if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))