
import re
from typing import Iterable


SKILL_CATEGORIES = {
    "Programming Languages": [
        "python", "java", "c++", "c#", "javascript", "typescript",
        "r", "sql", "php", "go", "rust",
    ],
    "Data Science and Machine Learning": [
        "machine learning", "deep learning", "data science",
        "data analysis", "data visualization",
        "natural language processing", "computer vision",
        "generative ai", "artificial intelligence", "statistics",
        "feature engineering", "model evaluation",
    ],
    "Python and Data Tools": [
        "pandas", "numpy", "scipy", "scikit-learn",
        "matplotlib", "seaborn", "jupyter", "excel", "power bi",
        "tableau",
    ],
    "Databases": [
        "mysql", "postgresql", "mongodb", "sqlite",
        "database management", "dbms", "database",
    ],
    "Web Development": [
        "html", "css", "react", "node.js", "express.js",
        "django", "flask", "fastapi", "streamlit", "rest api",
    ],
    "Tools and Platforms": [
        "git", "github", "docker", "linux", "aws", "azure",
        "google cloud", "visual studio code",
    ],
    "Core Computer Science": [
        "data structures", "algorithms",
        "object-oriented programming", "operating systems",
        "computer networks", "software engineering",
        "software testing",
    ],
}


# Different written forms mapped to one canonical skill.
SKILL_ALIASES = {
    "nlp": "natural language processing",
    "sklearn": "scikit-learn",
    "scikit learn": "scikit-learn",
    "powerbi": "power bi",
    "power-bi": "power bi",
    "js": "javascript",
    "ts": "typescript",
    "nodejs": "node.js",
    "node js": "node.js",
    "express": "express.js",
    "expressjs": "express.js",
    "oop": "object-oriented programming",
    "oops": "object-oriented programming",
    "object oriented programming": "object-oriented programming",
    "ml": "machine learning",
    "ai": "artificial intelligence",
    "google colab": "jupyter",
    "vscode": "visual studio code",
    "vs code": "visual studio code",
    "postgres": "postgresql",
    "mongo db": "mongodb",
    "restful api": "rest api",
}


def normalize_text(text: str) -> str:
    """Normalize case and whitespace without removing skill punctuation."""
    if not isinstance(text, str):
        raise TypeError("Input text must be a string.")

    return re.sub(r"\s+", " ", text.lower()).strip()


def normalize_skill(skill: str) -> str:
    """Convert a skill or alias to its canonical name."""
    normalized = normalize_text(skill)
    normalized = SKILL_ALIASES.get(normalized, normalized)
    return normalized


def _build_skill_pattern(skill: str) -> re.Pattern:
    """Match a complete skill phrase, allowing flexible whitespace."""
    words = skill.strip().split()

    if not words:
        raise ValueError("Skill name cannot be empty.")

    flexible_skill = r"\s+".join(re.escape(word) for word in words)

    return re.compile(
        rf"(?<![a-z0-9]){flexible_skill}(?![a-z0-9])",
        flags=re.IGNORECASE,
    )


def _all_canonical_skills() -> set[str]:
    """Return the unique canonical skills from the configured categories."""
    return {
        normalize_skill(skill)
        for category_skills in SKILL_CATEGORIES.values()
        for skill in category_skills
    }


def _skill_variants(canonical_skill: str) -> set[str]:
    """Return the canonical spelling and its configured aliases."""
    variants = {canonical_skill}

    for alias, canonical in SKILL_ALIASES.items():
        if canonical == canonical_skill:
            variants.add(alias)

    return variants


def _contains_skill(text: str, skill: str) -> bool:
    """Check all configured spellings of a canonical skill."""
    return any(
        _build_skill_pattern(variant).search(text)
        for variant in _skill_variants(skill)
    )


def extract_skills(
    text: str,
    extra_skills: Iterable[str] | None = None,
) -> list[str]:
    """
    Extract configured skills and optional recruiter-provided skills.

    Returns canonical skill names, avoiding duplicate aliases.
    """
    normalized_text = normalize_text(text)
    skills_to_check = _all_canonical_skills()

    if extra_skills:
        for skill in extra_skills:
            if isinstance(skill, str) and skill.strip():
                skills_to_check.add(normalize_skill(skill))

    found_skills = []

    for skill in sorted(skills_to_check):
        # A single-letter language such as R is too ambiguous to detect
        # safely with ordinary word matching in a resume.
        if skill == "r":
            continue

        if _contains_skill(normalized_text, skill):
            found_skills.append(skill)

    return sorted(set(found_skills))


def categorize_skills(
    skills: Iterable[str],
) -> dict[str, list[str]]:
    """Group canonical detected skills into configured categories."""
    normalized_skills = {
        normalize_skill(skill)
        for skill in skills
        if isinstance(skill, str) and skill.strip()
    }

    categorized = {}

    for category, category_skills in SKILL_CATEGORIES.items():
        canonical_category_skills = {
            normalize_skill(skill)
            for skill in category_skills
        }

        matches = sorted(
            normalized_skills.intersection(canonical_category_skills)
        )

        if matches:
            categorized[category] = matches

    return categorized


def analyze_resume_skills(text: str) -> dict:
    """Return detected skills, category groups, and method information."""
    skills = extract_skills(text)

    return {
        "skills": skills,
        "skill_count": len(skills),
        "categories": categorize_skills(skills),
        "method": "dictionary-based matching with canonical skill aliases",
        "limitation": (
            "A detected skill indicates that a configured skill name or "
            "alias appeared in the text. It does not verify proficiency, "
            "context, recency, or practical experience. The single-letter "
            "R language is skipped to reduce false positives."
        ),
    }
