
"""Candidate ranking using skill matching and optional semantic similarity."""

from __future__ import annotations

import math
from numbers import Real
from typing import Any

from services.matching_engine import match_candidate
from services.semantic_matcher import compare_texts


RESUME_DETAILS_TO_PRESERVE = (
     "email",
    "phone",
    "education",
    "experience",
    "projects",
    "certifications",
    "skills",
    "skill_count",
    "categories",
    "method",
    "skill_evidence",
    "skills_with_evidence",
    "skills_without_evidence",
    "evidence_count",
    "evidence_method",
)


RESUME_TEXT_KEYS = (
    "text",
    "full_text",
    "extracted_text",
    "raw_text",
    "content",
)


def _validate_semantic_weight(value: Real) -> float:
    """Validate semantic contribution as a finite number from 0 to 1."""
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError("Semantic weight must be a number.")

    if not math.isfinite(value):
        raise ValueError("Semantic weight must be finite.")

    if not 0.0 <= value <= 1.0:
        raise ValueError("Semantic weight must be between 0 and 1.")

    return float(value)


def _safe_copy(value: Any) -> Any:
    """Copy common mutable containers without changing source analyses."""
    if isinstance(value, dict):
        return value.copy()

    if isinstance(value, list):
        return value.copy()

    if isinstance(value, set):
        return value.copy()

    if isinstance(value, tuple):
        return tuple(value)

    return value


def _extract_resume_text(resume_analysis: dict) -> str:
    """Return the first available non-empty extracted-text field."""
    for key in RESUME_TEXT_KEYS:
        value = resume_analysis.get(key)

        if isinstance(value, str) and value.strip():
            return value.strip()

    return ""


def _validate_score(value: Any, name: str) -> float:
    """Convert a score to float and validate its range and finiteness."""
    if isinstance(value, bool):
        raise ValueError(f"{name} must be numeric, not boolean.")

    try:
        score = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be numeric.") from None

    if not math.isfinite(score):
        raise ValueError(f"{name} must be finite.")

    if not 0.0 <= score <= 100.0:
        raise ValueError(f"{name} must be between 0 and 100.")

    return score


def rank_candidates(
    resume_analyses: list[dict],
    job_analysis: dict,
    *,
    use_semantic: bool = False,
    job_description: str | None = None,
    semantic_weight: float = 0.35,
    semantic_model=None,
) -> list[dict]:
    """
    Rank candidates using skill matching, optionally combined with
    semantic similarity.

    semantic_weight represents the semantic score's contribution.
    For example, 0.35 means 35% semantic score and 65% skill score.

    Semantic matching is not run unless use_semantic=True.
    """
    if not isinstance(resume_analyses, list):
        raise TypeError("Resume analyses must be a list.")

    if not isinstance(job_analysis, dict):
        raise TypeError("Job analysis must be a dictionary.")

    if not isinstance(use_semantic, bool):
        raise TypeError("use_semantic must be a boolean.")

    weight = _validate_semantic_weight(semantic_weight)

    if use_semantic:
        if (
            not isinstance(job_description, str)
            or not job_description.strip()
        ):
            raise ValueError(
                "A non-empty job description is required "
                "when semantic matching is enabled."
            )

    if not resume_analyses:
        return []

    results = []

    for index, resume_analysis in enumerate(resume_analyses):
        if not isinstance(resume_analysis, dict):
            raise TypeError(
                "Each resume analysis must be a dictionary."
            )

        # Copy the source data so downstream scoring does not modify it.
        source = dict(resume_analysis)

        result = match_candidate(source, job_analysis)

        if not isinstance(result, dict):
            raise TypeError(
                "match_candidate() must return a dictionary."
            )

        result = dict(result)

        skill_score = _validate_score(
            result.get("match_score"),
            "Skill match score",
        )

        result["skill_match_score"] = round(skill_score, 2)

        if use_semantic:
            resume_text = _extract_resume_text(source)

            semantic_result = compare_texts(
                resume_text,
                job_description,
                model=semantic_model,
            )

            if not isinstance(semantic_result, dict):
                raise TypeError(
                    "compare_texts() must return a dictionary."
                )

            semantic_score = _validate_score(
                semantic_result.get("semantic_score"),
                "Semantic score",
            )

            combined_score = (
                skill_score * (1.0 - weight)
                + semantic_score * weight
            )

            result.update({
                "semantic_similarity": semantic_result.get(
                    "semantic_similarity"
                ),
                "semantic_score": round(semantic_score, 2),
                "semantic_model": semantic_result.get("model"),
                "semantic_limitation": semantic_result.get("limitation"),
                "semantic_weight": weight,
                "combined_score": round(combined_score, 2),
                "ranking_method": (
                    "Weighted combination of skill match and "
                    "semantic similarity"
                ),
            })

            if not resume_text:
                result["semantic_text_warning"] = (
                    "No non-empty resume text was found in the "
                    "supported text fields. Verify the resume "
                    "analyzer output before trusting this score."
                )
            else:
                result["semantic_text_warning"] = None

        else:
            result.update({
                "semantic_similarity": None,
                "semantic_score": None,
                "semantic_model": None,
                "semantic_limitation": None,
                "semantic_weight": 0.0,
                "combined_score": round(skill_score, 2),
                "ranking_method": "Skill matching baseline",
                "semantic_text_warning": None,
            })

        # Preserve compatibility with consumers of the legacy score field.
        result["match_score"] = result["combined_score"]

        # Preserve extracted resume information for the dashboard.
        for field in RESUME_DETAILS_TO_PRESERVE:
            if field in source:
                result[field] = _safe_copy(source[field])

        # Preserve extracted text fields for downstream diagnostics.
        for field in RESUME_TEXT_KEYS:
            if field in source:
                result[field] = _safe_copy(source[field])

        result["resume_extraction_limitation"] = source.get(
            "limitation", ""
        )
        result["input_order"] = index

        results.append(result)

    # Stable tie-breaking: equal scores retain upload order.
    results.sort(
        key=lambda candidate: (
            -candidate["match_score"],
            candidate["input_order"],
        )
    )

    for rank, candidate in enumerate(results, start=1):
        candidate["rank"] = rank
        candidate.pop("input_order", None)

    return results
