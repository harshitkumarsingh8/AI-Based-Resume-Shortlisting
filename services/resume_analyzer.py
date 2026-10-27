
"""Resume parsing, structured extraction, and skill evidence verification."""

import re
from pathlib import Path
from typing import Any


from utils.resume_parser import extract_resume_text
from services.skill_extractor import analyze_resume_skills


SECTION_ALIASES = {
    "education": [
        "education",
        "academic background",
        "educational background",
        "academic qualifications",
        "academic history",
    ],
    "experience": [
        "experience",
        "work experience",
        "professional experience",
        "employment history",
        "internship experience",
        "work history",
    ],
    "projects": [
        "projects",
        "personal projects",
        "academic projects",
        "key projects",
        "project experience",
    ],
    "certifications": [
        "certifications",
        "certificates",
        "licenses and certifications",
        "certification",
        "licenses",
    ],
}

OTHER_SECTION_HEADINGS = {
    "professional summary",
    "summary",
    "career objective",
    "objective",
    "technical skills",
    "skills",
    "key skills",
    "core competencies",
    "additional information",
    "personal information",
    "personal details",
    "contact",
    "contact information",
    "languages",
    "interests",
    "achievements",
    "awards",
    "references",
    "publications",
    "declaration",
    "hobbies",
}

ALL_SECTION_HEADINGS = {
    heading
    for headings in SECTION_ALIASES.values()
    for heading in headings
} | OTHER_SECTION_HEADINGS


def _clean_lines(text: str) -> list[str]:
    """Normalize whitespace and remove blank lines."""
    return [
        re.sub(r"\s+", " ", line).strip()
        for line in text.splitlines()
        if line.strip()
    ]


def _normalize_heading(line: str) -> str:
    """Normalize a possible resume section heading."""
    return re.sub(r"\s+", " ", line).strip().lower().rstrip(":").strip()


def _extract_email(text: str) -> str | None:
    """Return the first email address found."""
    match = re.search(
        r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
        text,
        flags=re.IGNORECASE,
    )
    return match.group(0) if match else None


def _extract_phone(text: str) -> str | None:
    """Find a phone-like number; this does not verify ownership."""
    pattern = re.compile(
        r"(?<!\w)(?:\+\s?\d{1,3}[\s().-]?)?"
        r"(?:\d[\d\s().-]{7,}\d)(?!\w)"
    )

    for match in pattern.finditer(text):
        candidate = match.group(0).strip()
        digits = re.sub(r"\D", "", candidate)

        if 10 <= len(digits) <= 15:
            return candidate

    return None


def _extract_candidate_name(lines: list[str]) -> str | None:
    """Suggest a candidate name from the opening lines."""
    ignored_labels = {
        "resume",
        "curriculum vitae",
        "cv",
        "profile",
        "contact",
        "personal details",
        "professional summary",
        "summary",
        "career objective",
        "objective",
    }

    for line in lines[:10]:
        candidate = line.strip(" |:-")
        normalized = _normalize_heading(candidate)

        if not candidate or normalized in ignored_labels:
            continue

        if "@" in candidate:
            continue

        if re.search(r"https?://|www\.", candidate, re.IGNORECASE):
            continue

        if re.search(
            r"\b(phone|mobile|email|linkedin|github|address)\s*:",
            candidate,
            re.IGNORECASE,
        ):
            continue

        if _extract_email(candidate) or _extract_phone(candidate):
            continue

        if len(candidate) > 70 or len(candidate.split()) > 6:
            continue

        if normalized in ALL_SECTION_HEADINGS:
            continue

        if re.search(r"[A-Za-z]", candidate):
            return candidate

    return None


def _split_inline_heading(line: str) -> tuple[str, str] | None:
    """Recognize lines such as 'Education: BCA'."""
    match = re.match(
        r"^\s*([A-Za-z][A-Za-z &/()-]{1,50}?)\s*[:\-]\s*(.*?)\s*$",
        line,
    )

    if not match:
        return None

    heading = _normalize_heading(match.group(1))
    content = match.group(2).strip()

    if heading in ALL_SECTION_HEADINGS:
        return heading, content

    return None


def _extract_section(text: str, aliases: list[str]) -> list[str]:
    """Extract a section until the next recognized heading."""
    lines = _clean_lines(text)
    target_headings = {_normalize_heading(item) for item in aliases}
    extracted = []
    collecting = False

    for line in lines:
        normalized = _normalize_heading(line)

        if normalized in ALL_SECTION_HEADINGS:
            if normalized in target_headings:
                collecting = True
            elif collecting:
                break
            continue

        inline_heading = _split_inline_heading(line)

        if inline_heading:
            heading, content = inline_heading

            if heading in target_headings:
                collecting = True
                if content:
                    extracted.append(content)
            elif collecting:
                break

            continue

        if collecting:
            extracted.append(line)

    return extracted


def _skill_search_pattern(skill: str) -> re.Pattern | None:
    """
    Build a case-insensitive search pattern for a skill label.

    Spaces in multiword labels can match variable whitespace.
    """
    skill = " ".join(skill.strip().split())

    if not skill:
        return None

    escaped = re.escape(skill)
    escaped = re.sub(r"(?:\\ )+", r"\\s+", escaped)

    # Avoid matching a short skill inside a longer word.
    return re.compile(
        rf"(?<!\w){escaped}(?!\w)",
        flags=re.IGNORECASE,
    )


def _extract_skill_evidence(
    text: str,
    skills: list[str],
    context_chars: int = 100,
) -> dict[str, Any]:
    """
    Find text snippets supporting each detected skill.

    Evidence means that the text contains a matching skill label.
    It does not establish proficiency, authenticity, or experience.
    """
    evidence = {}
    skills_with_evidence = []
    skills_without_evidence = []

    for skill in skills:
        pattern = _skill_search_pattern(skill)

        if pattern is None:
            evidence[skill] = []
            skills_without_evidence.append(skill)
            continue

        matches = []
        seen_snippets = set()

        for match in pattern.finditer(text):
            start = max(0, match.start() - context_chars)
            end = min(len(text), match.end() + context_chars)

            snippet = re.sub(
                r"\s+",
                " ",
                text[start:end],
            ).strip()

            key = snippet.casefold()

            if key not in seen_snippets:
                seen_snippets.add(key)
                matches.append({
                    "matched_text": match.group(0),
                    "snippet": snippet,
                    "start": match.start(),
                    "end": match.end(),
                })

            # Limit stored evidence to keep batch results manageable.
            if len(matches) >= 5:
                break

        evidence[skill] = matches

        if matches:
            skills_with_evidence.append(skill)
        else:
            skills_without_evidence.append(skill)

    return {
        "skill_evidence": evidence,
        "skills_with_evidence": skills_with_evidence,
        "skills_without_evidence": skills_without_evidence,
        "evidence_count": len(skills_with_evidence),
        "evidence_method": "case_insensitive_text_match",
    }


def analyze_resume(file_path: str | Path) -> dict:
    """
    Extract text, candidate details, sections, skills, and skill evidence.

    Evidence is a review aid, not proof of a candidate's proficiency.
    """
    path = Path(file_path)

    if not path.is_file():
        raise FileNotFoundError(f"Resume file not found: {path}")

    text = extract_resume_text(path)

    if not isinstance(text, str) or not text.strip():
        raise ValueError(
            "No readable text found in the resume. The PDF may be "
            "scanned, image-only, encrypted, or the document may be empty."
        )

    lines = _clean_lines(text)
    skill_analysis = analyze_resume_skills(text)

    skills = skill_analysis.get("skills", [])
    if not isinstance(skills, list):
        skills = []

    skills = [
        " ".join(skill.strip().split())
        for skill in skills
        if isinstance(skill, str) and skill.strip()
    ]

    # Deduplicate while preserving order.
    skills = list(dict.fromkeys(skills))

    categories = skill_analysis.get("categories", {})
    if not isinstance(categories, dict):
        categories = {}

    evidence_result = _extract_skill_evidence(text, skills)

    return {
        "filename": path.name,
        "text": text,
        "candidate_name": _extract_candidate_name(lines),
        "email": _extract_email(text),
        "phone": _extract_phone(text),
        "education": _extract_section(
            text, SECTION_ALIASES["education"]
        ),
        "experience": _extract_section(
            text, SECTION_ALIASES["experience"]
        ),
        "projects": _extract_section(
            text, SECTION_ALIASES["projects"]
        ),
        "certifications": _extract_section(
            text, SECTION_ALIASES["certifications"]
        ),
        "skills": skills,
        "skill_count": skill_analysis.get("skill_count", len(skills)),
        "categories": categories,
        "method": skill_analysis.get("method", "dictionary_matching"),

        # New evidence fields for recruiter verification.
        **evidence_result,

        "limitation": (
            "Skills are detected using the configured skill extractor. "
            "Evidence snippets show matching text, not verified proficiency "
            "or authenticity. Contact details and resume sections are "
            "identified heuristically and may be incomplete or incorrect. "
            "Scanned PDFs may require OCR. Human review is necessary "
            "before hiring decisions."
        ),
    }
