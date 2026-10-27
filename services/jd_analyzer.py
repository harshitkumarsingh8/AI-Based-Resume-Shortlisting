
from __future__ import annotations

import re
from typing import Any


# Canonical skill names and their recognized variants.
# Extend this dictionary as the project grows.
SKILL_ALIASES: dict[str, tuple[str, ...]] = {
    "python": ("python", "python programming"),
    "sql": ("sql", "structured query language"),
    "machine learning": ("machine learning", "machine-learning"),
    "deep learning": ("deep learning",),
    "artificial intelligence": ("artificial intelligence",),
    "generative ai": ("generative ai", "generative artificial intelligence"),
    "natural language processing": ("natural language processing", "nlp"),
    "pandas": ("pandas",),
    "numpy": ("numpy",),
    "scikit-learn": ("scikit-learn", "scikit learn", "sklearn"),
    "data analysis": ("data analysis", "data analytics"),
    "data science": ("data science",),
    "data visualization": ("data visualization", "data visualisation"),
    "statistics": ("statistics", "statistical analysis"),
    "probability": ("probability",),
    "feature engineering": ("feature engineering",),
    "model evaluation": ("model evaluation", "evaluate models"),
    "tensorflow": ("tensorflow",),
    "pytorch": ("pytorch", "py torch"),
    "docker": ("docker",),
    "kubernetes": ("kubernetes",),
    "aws": ("aws", "amazon web services"),
    "azure": ("azure", "microsoft azure"),
    "cloud computing": ("cloud computing",),
    "git": ("git",),
    "github": ("github",),
    "streamlit": ("streamlit",),
    "flask": ("flask",),
    "fastapi": ("fastapi", "fast api"),
    "api development": ("api development", "rest api", "rest apis"),
    "java": ("java", "java programming"),
    "c++": ("c++", "cpp"),
    "c": ("c programming", "c language"),
    "javascript": ("javascript",),
    "html": ("html",),
    "css": ("css",),
    "excel": ("excel", "microsoft excel"),
    "power bi": ("power bi", "powerbi"),
    "tableau": ("tableau",),
    "matplotlib": ("matplotlib",),
    "seaborn": ("seaborn",),
    "opencv": ("opencv", "open cv"),
    "llms": ("llm", "llms", "large language models"),
    "transformers": ("transformers library", "hugging face transformers"),
    "prompt engineering": ("prompt engineering",),
    "mysql": ("mysql",),
    "postgresql": ("postgresql", "postgres"),
    "mongodb": ("mongodb", "mongo db"),
    "linux": ("linux",),
    "data pipelines": ("data pipelines", "data pipeline"),
    "exploratory data analysis": ("exploratory data analysis", "eda"),
    "data structures": ("data structures", "data structure"),
    "algorithms": ("algorithms", "algorithm design"),
    "problem solving": ("problem-solving", "problem solving"),
    "communication": ("communication skills",),
    "teamwork": ("teamwork", "team collaboration"),
}


def _normalize(text: str) -> str:
    """Normalize casing and whitespace."""
    text = text.lower()
    text = text.replace("\u2013", "-").replace("\u2014", "-")
    return re.sub(r"\s+", " ", text).strip()


def _contains_phrase(text: str, phrase: str) -> bool:
    """Match a phrase without matching it inside a larger word."""
    phrase = _normalize(phrase)

    if not phrase:
        return False

    pattern = (
        r"(?<![a-z0-9+#])"
        + re.escape(phrase)
        + r"(?![a-z0-9+#])"
    )

    return re.search(pattern, text, flags=re.IGNORECASE) is not None


def _find_skills(text: str) -> list[str]:
    """
    Detect skills anywhere in the job description.

    Section headings do not determine skill priority.
    """
    normalized = _normalize(text)
    detected: list[str] = []

    for canonical_name, aliases in SKILL_ALIASES.items():
        if any(_contains_phrase(normalized, alias) for alias in aliases):
            detected.append(canonical_name)

    return sorted(detected)


def _extract_minimum_experience(text: str) -> float | None:
    """
    Extract a stated experience duration.

    Examples:
        '2 years of experience' -> 2.0
        'at least 1.5 years of experience' -> 1.5
        '3+ years of experience' -> 3.0

    This is a basic pattern-based extractor, not a full
    interpretation of every possible experience requirement.
    """
    normalized = _normalize(text)

    patterns = (
        r"\bminimum\s+(?:of\s+)?(\d+(?:\.\d+)?)\s+years?\b",
        r"\bat\s+least\s+(\d+(?:\.\d+)?)\s+years?\b",
        r"\b(\d+(?:\.\d+)?)\s*\+\s*years?\s+(?:of\s+)?experience\b",
        r"\b(\d+(?:\.\d+)?)\s+years?\s+(?:of\s+)?experience\b",
        r"\bexperience\s*:\s*(\d+(?:\.\d+)?)\s+years?\b",
    )

    for pattern in patterns:
        match = re.search(pattern, normalized)

        if match:
            return float(match.group(1))

    return None


def _extract_education_keywords(text: str) -> list[str]:
    """Detect common education-related terms."""
    terms = (
        "bachelor's degree",
        "bachelors degree",
        "bachelor degree",
        "bca",
        "b.tech",
        "btech",
        "b.e.",
        "computer science",
        "information technology",
        "related field",
        "master's degree",
        "masters degree",
        "mca",
        "m.tech",
        "mtech",
        "phd",
    )

    normalized = _normalize(text)

    return sorted(
        term
        for term in terms
        if _contains_phrase(normalized, term)
    )


def analyze_job_description(job_description: str) -> dict[str, Any]:
    """
    Analyze a job description.

    The analyzer detects skills and basic job metadata.
    It NEVER assigns Must-have, Important, or Preferred priorities.
    Those categories must be configured by the recruiter in the UI.

    Raises:
        TypeError: when input is not a string.
        ValueError: when input is empty or whitespace only.
    """
    if not isinstance(job_description, str):
        raise TypeError("Job description must be a string.")

    if not job_description.strip():
        raise ValueError("Job description cannot be empty.")

    description = re.sub(r"\s+", " ", job_description).strip()
    detected_skills = _find_skills(description)

    return {
        "job_description": description,
        "skills": detected_skills,
        "skill_count": len(detected_skills),

        # Recruiter selects these categories separately in the UI.
        "must_have_skills": [],
        "important_skills": [],
        "preferred_skills": [],

        # Alternatives are informational only; no automatic substitution.
        "skill_alternatives": {},
        "minimum_experience_years": _extract_minimum_experience(
            description
        ),
        "education_keywords": _extract_education_keywords(description),
        "method": "Dictionary-based skill detection",
        "limitation": (
            "Skill detection uses a predefined dictionary and may miss "
            "unlisted skills or interpret context imperfectly. Skills "
            "are detected without assigning priority categories. The "
            "recruiter must choose Must-have, Important, and Preferred "
            "skills before candidate scoring. Detected skills alone do "
            "not prove candidate proficiency or suitability."
        ),
    }
