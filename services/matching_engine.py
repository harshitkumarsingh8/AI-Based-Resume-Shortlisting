
from collections.abc import Mapping


PRIORITY_WEIGHTS = {
    "must_have": 3,
    "important": 2,
    "preferred": 1,
}


def _normalize_skills(skills) -> set[str]:
    """Normalize skill names for case-insensitive comparison."""
    if not isinstance(skills, (list, tuple, set)):
        raise TypeError("Skills must be a list, tuple, or set.")

    return {
        " ".join(skill.lower().split())
        for skill in skills
        if isinstance(skill, str) and skill.strip()
    }


def _validate_analysis(
    resume_analysis: dict,
    job_analysis: dict,
) -> None:
    """Validate the minimum input structure required for matching."""
    if not isinstance(resume_analysis, Mapping):
        raise TypeError("Resume analysis must be a dictionary.")

    if not isinstance(job_analysis, Mapping):
        raise TypeError("Job analysis must be a dictionary.")

    if "skills" not in resume_analysis:
        raise ValueError("Resume analysis must contain 'skills'.")

    if "skills" not in job_analysis:
        raise ValueError("Job analysis must contain 'skills'.")


def match_candidate(
    resume_analysis: dict,
    job_analysis: dict,
) -> dict:
    """
    Compare one analyzed resume against one analyzed job description.

    Priority weights:
        Must-have = 3
        Important = 2
        Preferred = 1

    The score is the weighted percentage of matched listed skills.
    It is not a prediction of job performance or hiring suitability.
    """
    _validate_analysis(resume_analysis, job_analysis)

    candidate_skills = _normalize_skills(resume_analysis["skills"])
    job_skills = _normalize_skills(job_analysis["skills"])

    if not job_skills:
        raise ValueError(
            "Job analysis contains no skills to compare."
        )

    priority_groups = {
        "must_have": _normalize_skills(
            job_analysis.get("must_have_skills", [])
        ),
        "important": _normalize_skills(
            job_analysis.get("important_skills", [])
        ),
        "preferred": _normalize_skills(
            job_analysis.get("preferred_skills", [])
        ),
    }

    # Keep only skills that actually appear in the job's full skill list.
    for priority in priority_groups:
        priority_groups[priority] &= job_skills

    # If the same skill appears in multiple priority groups,
    # assign it only to the highest priority group.
    assigned = set()

    for priority in ("must_have", "important", "preferred"):
        priority_groups[priority] -= assigned
        assigned.update(priority_groups[priority])

    # Preserve skills found in the JD but not assigned to a priority section.
    unclassified_skills = job_skills - assigned

    groups = {
        "must_have": priority_groups["must_have"],
        "important": priority_groups["important"],
        "preferred": priority_groups["preferred"],
        "unclassified": unclassified_skills,
    }

    group_results = {}
    matched_skills = set()
    missing_skills = set()
    total_weight = 0
    earned_weight = 0

    for priority, required_skills in groups.items():
        weight = PRIORITY_WEIGHTS.get(priority, 1)

        matched = sorted(required_skills & candidate_skills)
        missing = sorted(required_skills - candidate_skills)

        group_weight = len(required_skills) * weight
        matched_weight = len(matched) * weight

        total_weight += group_weight
        earned_weight += matched_weight

        matched_skills.update(matched)
        missing_skills.update(missing)

        group_results[priority] = {
            "required_skills": sorted(required_skills),
            "matched_skills": matched,
            "missing_skills": missing,
            "required_count": len(required_skills),
            "matched_count": len(matched),
            "weight_per_skill": weight,
        }

    score = round(
        (earned_weight / total_weight) * 100,
        2,
    ) if total_weight else 0.0

    return {
        "candidate_name": resume_analysis.get("candidate_name"),
        "filename": resume_analysis.get("filename"),
        "match_score": score,
        "matched_skills": sorted(matched_skills),
        "missing_skills": sorted(missing_skills),
        "matched_skill_count": len(matched_skills),
        "missing_skill_count": len(missing_skills),
        "total_job_skills": len(job_skills),
        "priority_breakdown": group_results,
        "scoring_method": (
            "Weighted skill overlap: must-have=3, important=2, "
            "preferred=1, unclassified=1."
        ),
        "limitation": (
            "This baseline compares skill names only. It does not assess "
            "skill proficiency, context, years of experience, education "
            "eligibility, or semantic similarity. The score is not a "
            "probability of hiring success."
        ),
    }
