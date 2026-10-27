
"""Recruiter-configurable, explainable resume shortlisting."""

from __future__ import annotations

import math
from numbers import Real
from typing import Any, Iterable


DEFAULT_WEIGHTS = {
    "must_have": 0.60,
    "important": 0.25,
    "preferred": 0.15,
}

CATEGORIES = ("must_have", "important", "preferred")


def _skills(value: Any) -> list[str]:
    """Normalize a skill collection and remove case-insensitive duplicates."""
    if value is None:
        return []

    if isinstance(value, str):
        value = [value]

    if not isinstance(value, (list, tuple, set)):
        return []

    result = []
    seen = set()

    for item in value:
        if not isinstance(item, str):
            continue

        item = " ".join(item.strip().split())
        key = item.casefold()

        if item and key not in seen:
            seen.add(key)
            result.append(item)

    return result


def _normalise_weights(
    weights: dict[str, float] | None,
) -> dict[str, float]:
    """Validate category weights and ensure that they total 100%."""
    if weights is None:
        weights = DEFAULT_WEIGHTS.copy()

    if not isinstance(weights, dict):
        raise TypeError("weights must be a dictionary.")

    result = {}

    for category in CATEGORIES:
        value = weights.get(category, 0)

        if isinstance(value, bool):
            raise ValueError(f"Invalid weight for {category}.")

        try:
            value = float(value)
        except (TypeError, ValueError):
            raise ValueError(
                f"Invalid weight for {category}."
            ) from None

        if not math.isfinite(value) or not 0 <= value <= 1:
            raise ValueError(
                f"Weight for {category} must be between 0 and 1."
            )

        result[category] = value

    if abs(sum(result.values()) - 1.0) > 1e-6:
        raise ValueError("Category weights must total 1.0 (100%).")

    return result


def _validate_percentage(value: Real, name: str) -> float:
    """Validate a percentage from 0 to 100."""
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{name} must be numeric.")

    result = float(value)

    if not math.isfinite(result) or not 0 <= result <= 100:
        raise ValueError(f"{name} must be between 0 and 100.")

    return result


def configure_candidate_priorities(
    priorities: dict[str, Iterable[str]],
) -> dict[str, list[str]]:
    """Validate skill categories and prohibit duplicate assignments."""
    if not isinstance(priorities, dict):
        raise TypeError("priorities must be a dictionary.")

    configured = {
        category: _skills(priorities.get(category, []))
        for category in CATEGORIES
    }

    owners = {}

    for category, category_skills in configured.items():
        for skill in category_skills:
            key = skill.casefold()

            if key in owners:
                raise ValueError(
                    f"Skill '{skill}' appears in both "
                    f"{owners[key]} and {category}."
                )

            owners[key] = category

    if not any(configured.values()):
        raise ValueError("Select at least one skill.")

    return configured


def _candidate_skills(candidate: dict[str, Any]) -> list[str]:
    """Read skills from supported analysis output fields."""
    for key in (
        "skills",
        "extracted_skills",
        "technical_skills",
    ):
        found = _skills(candidate.get(key))

        if found:
            return found

    return []


def _normalise_alternative_groups(
    value: Any,
) -> list[list[str]]:
    """
    Normalize alternative skill groups.

    Supported examples:
        [["tensorflow", "pytorch"], ["aws", "azure"]]
        [{"skills": ["tensorflow", "pytorch"]}]
        [{"alternatives": ["aws", "azure"]}]
        {"framework": ["tensorflow", "pytorch"]}

    Invalid or single-skill groups are ignored.
    """
    if value is None:
        return []

    if isinstance(value, dict):
        if any(
            key in value
            for key in ("skills", "alternatives", "options")
        ):
            value = [value]
        else:
            value = list(value.values())

    if not isinstance(value, (list, tuple, set)):
        return []

    groups = []
    seen_groups = set()

    for item in value:
        if isinstance(item, dict):
            members = item.get(
                "skills",
                item.get(
                    "alternatives",
                    item.get("options", []),
                ),
            )
        else:
            members = item

        members = _skills(members)

        if len(members) < 2:
            continue

        group_key = frozenset(
            skill.casefold() for skill in members
        )

        if group_key in seen_groups:
            continue

        seen_groups.add(group_key)
        groups.append(members)

    return groups


def _group_category_skills(
    required: list[str],
    alternative_groups: list[list[str]],
) -> list[list[str]]:
    """
    Convert skills into scoring units.

    Skills in the same alternative group count as one requirement
    only when at least two group members occur in this skill list.
    """
    required_keys = {skill.casefold() for skill in required}
    units = []
    consumed = set()

    for group in alternative_groups:
        members = [
            skill
            for skill in group
            if skill.casefold() in required_keys
        ]

        if len(members) < 2:
            continue

        member_keys = {
            skill.casefold() for skill in members
        }

        if member_keys & consumed:
            continue

        units.append(members)
        consumed.update(member_keys)

    for skill in required:
        key = skill.casefold()

        if key not in consumed:
            units.append([skill])

    return units


def _score_skill_units(
    units: list[list[str]],
    candidate_keys: set[str],
) -> dict[str, Any]:
    """Score skills or requirements, respecting alternative groups."""
    matched_skills = []
    missing_skills = []
    matched_units = 0

    for unit in units:
        present = [
            skill
            for skill in unit
            if skill.casefold() in candidate_keys
        ]

        if present:
            matched_units += 1
            matched_skills.extend(present)
        else:
            missing_skills.extend(unit)

    total_units = len(units)

    coverage = (
        100.0 * matched_units / total_units
        if total_units
        else 0.0
    )

    return {
        "matched": len(matched_skills),
        "missing": len(missing_skills),
        "matched_skills": matched_skills,
        "missing_skills": missing_skills,
        "matched_units": matched_units,
        "total_units": total_units,
        "coverage": round(coverage, 2),
    }


def shortlist_candidates(
    candidates: list[dict[str, Any]],
    priorities: dict[str, Iterable[str]],
    weights: dict[str, float] | None = None,
    score_threshold: float = 70,
    min_must_have_coverage: float = 80,
    job_skills: Iterable[str] | None = None,
    *,
    use_semantic: bool = False,
    semantic_weight: float = 0.0,
    skill_alternatives: Any = None,
) -> list[dict[str, Any]]:
    """
    Calculate recruiter-priority scores and optional semantic blending.

    Semantic mode OFF:
        final score = recruiter-priority skill score

    Semantic mode ON:
        final score = skill score * (1 - semantic weight)
                    + semantic score * semantic weight

    Must-have eligibility is checked separately.

    full_jd_coverage:
        Matched individual JD skills / total individual JD skills.

    full_jd_requirement_coverage:
        Matched JD requirement units / total requirement units.
        Alternative groups can count as one requirement unit.
    """
    if not isinstance(candidates, list):
        raise TypeError("candidates must be a list.")

    if not isinstance(use_semantic, bool):
        raise TypeError("use_semantic must be a boolean.")

    if (
        isinstance(semantic_weight, bool)
        or not isinstance(semantic_weight, Real)
    ):
        raise TypeError("semantic_weight must be numeric.")

    semantic_weight = float(semantic_weight)

    if (
        not math.isfinite(semantic_weight)
        or not 0 <= semantic_weight <= 1
    ):
        raise ValueError("semantic_weight must be between 0 and 1.")

    if not use_semantic:
        semantic_weight = 0.0

    configured = configure_candidate_priorities(priorities)
    normalized_weights = _normalise_weights(weights)

    score_threshold = _validate_percentage(
        score_threshold,
        "score_threshold",
    )

    min_must_have_coverage = _validate_percentage(
        min_must_have_coverage,
        "min_must_have_coverage",
    )

    alternative_groups = _normalise_alternative_groups(
        skill_alternatives
    )

    if job_skills is None:
        all_jd_skills = _skills(
            configured["must_have"]
            + configured["important"]
            + configured["preferred"]
        )
    else:
        all_jd_skills = _skills(list(job_skills))

    # Keep individual skill coverage and grouped requirement
    # coverage as separate calculations.
    jd_units = _group_category_skills(
        all_jd_skills,
        alternative_groups,
    )

    output = []

    for original in candidates:
        if not isinstance(original, dict):
            continue

        candidate = dict(original)

        candidate_skills = _candidate_skills(candidate)
        candidate_keys = {
            skill.casefold() for skill in candidate_skills
        }

        category_scores = {}
        skill_score = 0.0

        for category in CATEGORIES:
            required = configured[category]

            units = _group_category_skills(
                required,
                alternative_groups,
            )

            details = _score_skill_units(
                units,
                candidate_keys,
            )

            contribution = (
                details["coverage"]
                * normalized_weights[category]
            )

            skill_score += contribution

            category_scores[category] = {
                **details,
                "weight": round(
                    normalized_weights[category] * 100,
                    2,
                ),
                "contribution": round(contribution, 2),
            }

        semantic_score = candidate.get("semantic_score")

        if use_semantic:
            if semantic_score is None:
                raise ValueError(
                    "Semantic matching is enabled, but a candidate "
                    "has no semantic_score. Re-run resume analysis "
                    "with semantic matching enabled."
                )

            if isinstance(semantic_score, bool):
                raise ValueError(
                    "Candidate semantic_score must be numeric."
                )

            try:
                semantic_score = float(semantic_score)
            except (TypeError, ValueError):
                raise ValueError(
                    "Candidate semantic_score must be numeric."
                ) from None

            if (
                not math.isfinite(semantic_score)
                or not 0 <= semantic_score <= 100
            ):
                raise ValueError(
                    "Candidate semantic_score must be between 0 and 100."
                )

            final_score = (
                skill_score * (1.0 - semantic_weight)
                + semantic_score * semantic_weight
            )
        else:
            semantic_score = None
            final_score = skill_score

        # Must-have coverage and eligibility.
        must_skills = configured["must_have"]

        must_units = _group_category_skills(
            must_skills,
            alternative_groups,
        )

        must_details = _score_skill_units(
            must_units,
            candidate_keys,
        )

        must_coverage = must_details["coverage"]

        must_eligible = (
            bool(must_skills)
            and must_coverage >= min_must_have_coverage
        )

        shortlisted = (
            final_score >= score_threshold
            and must_eligible
        )

        # Full JD matching. Matched/missing lists contain individual
        # skill names, while requirement coverage counts grouped units.
        matched_jd_details = _score_skill_units(
            jd_units,
            candidate_keys,
        )

        matched_jd = matched_jd_details["matched_skills"]
        missing_jd = matched_jd_details["missing_skills"]

        # Individual-skill coverage does not collapse alternatives.
        matched_jd_keys = {
            skill.casefold() for skill in matched_jd
        }

        total_individual_jd_skills = len(all_jd_skills)

        full_jd_skill_coverage = (
            round(
                100.0
                * len(matched_jd_keys)
                / total_individual_jd_skills,
                2,
            )
            if total_individual_jd_skills
            else 0.0
        )

        # Requirement coverage counts alternative groups as one unit.
        full_jd_requirement_coverage = (
            round(
                100.0
                * matched_jd_details["matched_units"]
                / matched_jd_details["total_units"],
                2,
            )
            if matched_jd_details["total_units"]
            else 0.0
        )

        reasons = []

        if not must_skills:
            reasons.append(
                "No must-have skills were configured."
            )
        elif not must_eligible:
            reasons.append(
                f"Must-have coverage {must_coverage:.2f}% is below "
                f"the required {min_must_have_coverage:.2f}%."
            )

        if final_score < score_threshold:
            reasons.append(
                f"Final score {final_score:.2f}% is below "
                f"the required {score_threshold:.2f}%."
            )

        if shortlisted:
            reasons.append(
                "Candidate meets both the score threshold "
                "and must-have eligibility requirement."
            )

        candidate.update({
            "priority_skill_score": round(skill_score, 2),
            "semantic_score": (
                round(semantic_score, 2)
                if semantic_score is not None
                else None
            ),
            "semantic_weight": semantic_weight,
            "shortlisting_score": round(final_score, 2),
            "match_score": round(final_score, 2),
            "must_have_coverage": round(must_coverage, 2),
            "must_have_eligible": must_eligible,
            "shortlisted": shortlisted,
            "shortlisting_status": (
                "Shortlisted"
                if shortlisted
                else "Not shortlisted"
            ),
            "shortlisting_reasons": reasons,
            "category_scores": category_scores,
            "shortlisting_weights": normalized_weights.copy(),

            # Full JD matched/missing skill lists.
            "full_jd_matched_skills": matched_jd,
            "full_jd_missing_skills": missing_jd,

            # Individual skills coverage.
            "full_jd_coverage": full_jd_skill_coverage,
            "full_jd_skill_coverage": full_jd_skill_coverage,

            # Requirement-unit coverage, including alternatives.
            "full_jd_requirement_coverage": (
                full_jd_requirement_coverage
            ),

            "full_jd_matched_requirement_units": (
                matched_jd_details["matched_units"]
            ),
            "full_jd_total_requirement_units": (
                matched_jd_details["total_units"]
            ),

            "priority_breakdown": {
                category: category_scores[category]
                for category in CATEGORIES
            },
            "alternative_skill_groups": alternative_groups,
        })

        output.append(candidate)

    output.sort(
        key=lambda item: (
            not item["shortlisted"],
            -item["shortlisting_score"],
        )
    )

    for rank, candidate in enumerate(output, start=1):
        candidate["rank"] = rank

    return output
