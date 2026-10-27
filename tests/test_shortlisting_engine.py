"""Regression tests for services.shortlisting_engine."""

import pytest

from services.shortlisting_engine import (
    configure_candidate_priorities,
    shortlist_candidates,
)


# ============================================================
# PRIORITY CONFIGURATION
# ============================================================

def test_configure_priorities_accepts_many_skills():
    skills = [f"skill_{i}" for i in range(150)]

    configured = configure_candidate_priorities({
        "must_have": skills,
    })

    assert len(configured["must_have"]) == 150
    assert configured["important"] == []
    assert configured["preferred"] == []


def test_configure_priorities_deduplicates_within_category():
    configured = configure_candidate_priorities({
        "must_have": ["Python", " python ", "SQL", "SQL"],
        "important": ["Git"],
        "preferred": ["Pandas"],
    })

    assert configured["must_have"] == ["Python", "SQL"]
    assert configured["important"] == ["Git"]
    assert configured["preferred"] == ["Pandas"]


def test_duplicate_skill_across_categories_is_rejected():
    with pytest.raises(ValueError, match="appears in both"):
        configure_candidate_priorities({
            "must_have": ["Python"],
            "important": ["python"],
        })


def test_empty_priorities_are_rejected():
    with pytest.raises(ValueError, match="at least one skill"):
        configure_candidate_priorities({})


def test_invalid_priority_container_is_rejected():
    with pytest.raises(
        TypeError,
        match="priorities must be a dictionary",
    ):
        configure_candidate_priorities(["Python"])


# ============================================================
# CORE SCORING AND SHORTLIST ELIGIBILITY
# ============================================================

def test_weighted_score_and_shortlisting():
    priorities = {
        "must_have": ["Python", "SQL"],
        "important": ["Pandas"],
        "preferred": ["Git"],
    }

    candidates = [
        {
            "name": "Candidate A",
            "skills": ["Python", "SQL", "Pandas", "Git"],
        },
        {
            "name": "Candidate B",
            "skills": ["Python", "Pandas", "Git"],
        },
    ]

    results = shortlist_candidates(
        candidates,
        priorities,
        score_threshold=70,
        min_must_have_coverage=80,
    )

    by_name = {
        item["name"]: item
        for item in results
    }

    assert by_name["Candidate A"]["shortlisting_score"] == 100.0
    assert by_name["Candidate A"]["shortlisted"] is True

    # Default weights: 60% Must-have, 25% Important, 15% Preferred.
    # Candidate B: 30 + 25 + 15 = 70.
    assert by_name["Candidate B"]["shortlisting_score"] == 70.0
    assert by_name["Candidate B"]["must_have_coverage"] == 50.0
    assert by_name["Candidate B"]["shortlisted"] is False


def test_full_match_gets_100_percent_score():
    priorities = {
        "must_have": ["Python", "Pandas"],
        "important": ["SQL"],
        "preferred": ["Git"],
    }

    result = shortlist_candidates(
        [{
            "name": "Complete",
            "skills": ["Python", "Pandas", "SQL", "Git"],
        }],
        priorities,
        weights={
            "must_have": 0.5,
            "important": 0.3,
            "preferred": 0.2,
        },
        score_threshold=70,
        min_must_have_coverage=80,
        job_skills=["Python", "Pandas", "SQL", "Git"],
    )

    candidate = result[0]

    assert candidate["shortlisting_score"] == 100.0
    assert candidate["must_have_coverage"] == 100.0
    assert candidate["must_have_eligible"] is True
    assert candidate["shortlisted"] is True
    assert candidate["rank"] == 1


def test_missing_one_of_two_must_have_skills_yields_50_percent():
    priorities = {
        "must_have": ["Python", "Pandas"],
        "important": ["SQL"],
        "preferred": ["Git"],
    }

    result = shortlist_candidates(
        [{
            "name": "Partial",
            "skills": ["Python", "SQL", "Git"],
        }],
        priorities,
        weights={
            "must_have": 0.5,
            "important": 0.3,
            "preferred": 0.2,
        },
        score_threshold=70,
        min_must_have_coverage=80,
        job_skills=["Python", "Pandas", "SQL", "Git"],
    )

    candidate = result[0]

    assert candidate["must_have_coverage"] == 50.0
    assert candidate["must_have_eligible"] is False
    assert candidate["shortlisted"] is False
    assert "Pandas" in candidate["full_jd_missing_skills"]
    assert "Python" in candidate["full_jd_matched_skills"]


def test_missing_must_have_skill_prevents_shortlisting():
    results = shortlist_candidates(
        [{"name": "A", "skills": ["Python"]}],
        {"must_have": ["Python", "SQL"]},
        score_threshold=0,
        min_must_have_coverage=80,
    )

    assert results[0]["must_have_eligible"] is False
    assert results[0]["shortlisted"] is False

    assert any(
        "Must-have coverage" in reason
        for reason in results[0]["shortlisting_reasons"]
    )


def test_no_must_have_skills_never_shortlists():
    results = shortlist_candidates(
        [{"name": "A", "skills": ["Python"]}],
        {"important": ["Python"]},
        score_threshold=0,
        min_must_have_coverage=0,
    )

    assert results[0]["must_have_eligible"] is False
    assert results[0]["shortlisted"] is False

    assert any(
        "No must-have skills" in reason
        for reason in results[0]["shortlisting_reasons"]
    )


def test_overall_score_threshold_is_independent_of_must_have_threshold():
    priorities = {
        "must_have": ["Python", "Pandas"],
        "important": ["SQL"],
        "preferred": ["Git"],
    }

    result = shortlist_candidates(
        [{
            "name": "LowScore",
            "skills": ["Python", "Pandas"],
        }],
        priorities,
        weights={
            "must_have": 0.5,
            "important": 0.3,
            "preferred": 0.2,
        },
        score_threshold=70,
        min_must_have_coverage=80,
        job_skills=["Python", "Pandas", "SQL", "Git"],
    )

    candidate = result[0]

    assert candidate["must_have_coverage"] == 100.0
    assert candidate["shortlisting_score"] == 50.0
    assert candidate["must_have_eligible"] is True
    assert candidate["shortlisted"] is False

    assert any(
        "Final score" in reason
        for reason in candidate["shortlisting_reasons"]
    )


def test_coverage_threshold_boundary_is_inclusive():
    result = shortlist_candidates(
        [{
            "name": "Boundary",
            "skills": ["Python", "SQL", "Pandas"],
        }],
        {
            "must_have": ["Python", "SQL", "Pandas", "Java"],
        },
        weights={
            "must_have": 1.0,
            "important": 0.0,
            "preferred": 0.0,
        },
        score_threshold=0,
        min_must_have_coverage=75,
    )

    assert result[0]["must_have_coverage"] == 75.0
    assert result[0]["must_have_eligible"] is True
    assert result[0]["shortlisted"] is True


def test_empty_category_does_not_add_free_score():
    results = shortlist_candidates(
        [{"name": "A", "skills": ["Python"]}],
        {
            "must_have": ["Python"],
            "important": ["SQL"],
        },
        weights={
            "must_have": 0.6,
            "important": 0.25,
            "preferred": 0.15,
        },
        score_threshold=0,
        min_must_have_coverage=80,
    )

    assert results[0]["shortlisting_score"] == 60.0

    assert (
        results[0]["category_scores"]["important"]["contribution"]
        == 0.0
    )

    assert (
        results[0]["category_scores"]["preferred"]["contribution"]
        == 0.0
    )


# ============================================================
# FULL JOB DESCRIPTION COVERAGE
# ============================================================

def test_full_job_description_coverage():
    results = shortlist_candidates(
        [{"name": "A", "skills": ["Python", "SQL"]}],
        {"must_have": ["Python"]},
        job_skills=["Python", "SQL", "Pandas"],
    )

    candidate = results[0]

    assert candidate["full_jd_matched_skills"] == ["Python", "SQL"]
    assert candidate["full_jd_missing_skills"] == ["Pandas"]

    assert candidate["full_jd_coverage"] == pytest.approx(
        66.67,
        abs=0.01,
    )

    assert candidate["full_jd_skill_coverage"] == pytest.approx(
        66.67,
        abs=0.01,
    )


def test_empty_job_skills_have_zero_coverage():
    result = shortlist_candidates(
        [{"name": "A", "skills": ["Python"]}],
        {"must_have": ["Python"]},
        job_skills=[],
    )

    assert result[0]["full_jd_matched_skills"] == []
    assert result[0]["full_jd_missing_skills"] == []
    assert result[0]["full_jd_coverage"] == 0.0


# ============================================================
# ALTERNATIVE SKILL REQUIREMENTS
# ============================================================

def test_alternative_skills_count_as_one_requirement():
    result = shortlist_candidates(
        [{"name": "TorchUser", "skills": ["PyTorch"]}],
        {"must_have": ["TensorFlow", "PyTorch"]},
        weights={
            "must_have": 1.0,
            "important": 0.0,
            "preferred": 0.0,
        },
        score_threshold=70,
        min_must_have_coverage=80,
        job_skills=["TensorFlow", "PyTorch"],
        skill_alternatives=[["TensorFlow", "PyTorch"]],
    )

    candidate = result[0]

    assert candidate["must_have_coverage"] == 100.0
    assert candidate["full_jd_requirement_coverage"] == 100.0
    assert candidate["full_jd_coverage"] == 50.0
    assert candidate["shortlisted"] is True


def test_duplicate_alternative_group_does_not_double_count_requirements():
    result = shortlist_candidates(
        [{"name": "TorchUser", "skills": ["PyTorch"]}],
        {"must_have": ["TensorFlow", "PyTorch"]},
        weights={
            "must_have": 1.0,
            "important": 0.0,
            "preferred": 0.0,
        },
        score_threshold=0,
        min_must_have_coverage=0,
        job_skills=["TensorFlow", "PyTorch"],
        skill_alternatives=[
            ["TensorFlow", "PyTorch"],
            ["PyTorch", "TensorFlow"],
        ],
    )

    assert result[0]["must_have_coverage"] == 100.0
    assert result[0]["full_jd_requirement_coverage"] == 100.0


# ============================================================
# WEIGHTS AND INPUT VALIDATION
# ============================================================

def test_invalid_weights_are_rejected():
    with pytest.raises(ValueError, match="must total 1.0"):
        shortlist_candidates(
            [{"skills": ["Python"]}],
            {"must_have": ["Python"]},
            weights={
                "must_have": 0.8,
                "important": 0.3,
                "preferred": 0.0,
            },
        )


def test_weight_outside_range_is_rejected():
    with pytest.raises(ValueError, match="between 0 and 1"):
        shortlist_candidates(
            [{"skills": ["Python"]}],
            {"must_have": ["Python"]},
            weights={
                "must_have": 1.1,
                "important": 0.0,
                "preferred": 0.0,
            },
        )


def test_score_threshold_outside_range_is_rejected():
    with pytest.raises(
        ValueError,
        match="score_threshold must be between 0 and 100",
    ):
        shortlist_candidates(
            [{"skills": ["Python"]}],
            {"must_have": ["Python"]},
            score_threshold=101,
        )


def test_must_have_coverage_threshold_outside_range_is_rejected():
    with pytest.raises(
        ValueError,
        match="min_must_have_coverage must be between 0 and 100",
    ):
        shortlist_candidates(
            [{"skills": ["Python"]}],
            {"must_have": ["Python"]},
            min_must_have_coverage=-1,
        )


def test_semantic_weight_outside_range_is_rejected():
    with pytest.raises(
        ValueError,
        match="semantic_weight must be between 0 and 1",
    ):
        shortlist_candidates(
            [{
                "skills": ["Python"],
                "semantic_score": 80,
            }],
            {"must_have": ["Python"]},
            use_semantic=True,
            semantic_weight=1.2,
        )


# ============================================================
# SEMANTIC SCORE BLENDING
# ============================================================

def test_semantic_blend_is_calculated_correctly():
    result = shortlist_candidates(
        [{
            "name": "Semantic",
            "skills": ["Python", "Pandas", "SQL", "Git"],
            "semantic_score": 60,
        }],
        {
            "must_have": ["Python", "Pandas"],
            "important": ["SQL"],
            "preferred": ["Git"],
        },
        weights={
            "must_have": 0.5,
            "important": 0.3,
            "preferred": 0.2,
        },
        score_threshold=0,
        min_must_have_coverage=0,
        job_skills=["Python", "Pandas", "SQL", "Git"],
        use_semantic=True,
        semantic_weight=0.25,
    )

    # 100 * 0.75 + 60 * 0.25 = 90.
    assert result[0]["priority_skill_score"] == 100.0
    assert result[0]["shortlisting_score"] == 90.0
    assert result[0]["semantic_score"] == 60.0
    assert result[0]["semantic_weight"] == 0.25
    assert result[0]["shortlisted"] is True


def test_semantic_mode_rejects_missing_semantic_score():
    with pytest.raises(ValueError, match="no semantic_score"):
        shortlist_candidates(
            [{
                "name": "MissingSemantic",
                "skills": ["Python"],
            }],
            {"must_have": ["Python"]},
            use_semantic=True,
            semantic_weight=0.3,
        )


def test_semantic_score_is_ignored_when_semantic_mode_is_disabled():
    result = shortlist_candidates(
        [{
            "name": "NoSemantic",
            "skills": ["Python"],
            "semantic_score": 20,
        }],
        {"must_have": ["Python"]},
        weights={
            "must_have": 1.0,
            "important": 0.0,
            "preferred": 0.0,
        },
        use_semantic=False,
        semantic_weight=0.8,
        score_threshold=0,
        min_must_have_coverage=0,
    )

    assert result[0]["priority_skill_score"] == 100.0
    assert result[0]["shortlisting_score"] == 100.0
    assert result[0]["semantic_score"] is None
    assert result[0]["semantic_weight"] == 0.0


def test_semantic_score_outside_range_is_rejected():
    with pytest.raises(ValueError, match="between 0 and 100"):
        shortlist_candidates(
            [{
                "name": "BadSemantic",
                "skills": ["Python"],
                "semantic_score": 101,
            }],
            {"must_have": ["Python"]},
            use_semantic=True,
            semantic_weight=0.3,
        )


# ============================================================
# CANDIDATE RANKING
# ============================================================

def test_candidates_are_ranked_with_shortlisted_first():
    results = shortlist_candidates(
        [
            {"name": "Low", "skills": ["Python"]},
            {"name": "High", "skills": ["Python", "SQL"]},
        ],
        {"must_have": ["Python", "SQL"]},
        score_threshold=60,
        min_must_have_coverage=80,
    )

    assert results[0]["name"] == "High"
    assert results[0]["rank"] == 1
    assert results[0]["shortlisted"] is True
    assert results[1]["rank"] == 2


def test_candidates_with_equal_eligibility_are_sorted_by_score_descending():
    results = shortlist_candidates(
        [
            {"name": "Medium", "skills": ["Python", "SQL"]},
            {"name": "High", "skills": ["Python", "SQL", "Pandas"]},
        ],
        {
            "must_have": ["Python"],
            "important": ["SQL", "Pandas"],
        },
        weights={
            "must_have": 0.5,
            "important": 0.5,
            "preferred": 0.0,
        },
        score_threshold=0,
        min_must_have_coverage=0,
    )

    assert results[0]["name"] == "High"

    assert (
        results[0]["shortlisting_score"]
        >= results[1]["shortlisting_score"]
    )

    assert results[0]["rank"] == 1
    assert results[1]["rank"] == 2


def test_non_dictionary_candidate_entries_are_skipped():
    result = shortlist_candidates(
        [
            None,
            "invalid",
            {"name": "Valid", "skills": ["Python"]},
        ],
        {"must_have": ["Python"]},
        score_threshold=0,
        min_must_have_coverage=0,
    )

    assert len(result) == 1
    assert result[0]["name"] == "Valid"
    assert result[0]["rank"] == 1


def test_candidate_skill_alias_fields_are_supported():
    result = shortlist_candidates(
        [{
            "name": "AliasField",
            "extracted_skills": ["Python"],
        }],
        {"must_have": ["Python"]},
        weights={
            "must_have": 1.0,
            "important": 0.0,
            "preferred": 0.0,
        },
        score_threshold=0,
        min_must_have_coverage=0,
    )

    assert result[0]["shortlisting_score"] == 100.0
    assert result[0]["shortlisted"] is True


# ============================================================
# RUN DIRECTLY
# ============================================================

if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))