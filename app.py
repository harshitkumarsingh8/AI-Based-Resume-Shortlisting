from __future__ import annotations

import re
import tempfile
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from services.resume_analyzer import analyze_resume
from services.jd_analyzer import analyze_job_description
from services.candidate_ranker import rank_candidates
from services.shortlisting_engine import (
    configure_candidate_priorities,
    shortlist_candidates,
)


# ============================================================
# PAGE CONFIGURATION
# ============================================================

st.set_page_config(
    page_title="AI-Based Resume Shortlisting",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ============================================================
# SESSION STATE
# ============================================================

DEFAULT_STATE = {
    "analysed_candidates": [],
    "ranked_candidates": [],
    "final_candidates": [],
    "job_analysis": None,
    "job_description": "",
    "analysis_ready": False,
    "analysis_complete": False,
    "analysis_settings": {},
    "priority_selections": {},
}

for key, value in DEFAULT_STATE.items():
    if key not in st.session_state:
        st.session_state[key] = value


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def first_value(
    data: dict[str, Any],
    keys: tuple[str, ...],
    default: Any = None,
) -> Any:
    """Return the first available, non-empty dictionary value."""
    for key in keys:
        value = data.get(key)
        if value is not None and value != "":
            return value
    return default


def as_list(value: Any) -> list:
    """Convert a value to a list without splitting strings."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, (tuple, set)):
        return list(value)
    if isinstance(value, str):
        return [value] if value.strip() else []
    return [value]


def as_text(value: Any) -> str:
    """Convert structured values to readable display text."""
    if value is None:
        return "Not available"

    if isinstance(value, (list, tuple, set)):
        return ", ".join(map(str, value)) or "Not available"

    if isinstance(value, dict):
        return (
            ", ".join(f"{key}: {item}" for key, item in value.items())
            or "Not available"
        )

    return str(value).strip() or "Not available"


def candidate_name(candidate: dict[str, Any]) -> str:
    return str(
        first_value(
            candidate,
            ("candidate_name", "name", "filename"),
            "Unknown Candidate",
        )
    )


def candidate_score(candidate: dict[str, Any]) -> float:
    """Prefer the final shortlisting score when available."""
    value = first_value(
        candidate,
        (
            "shortlisting_score",
            "match_score",
            "final_score",
            "overall_score",
            "total_score",
            "score",
        ),
        0,
    )

    try:
        score = float(value)
    except (TypeError, ValueError):
        return 0.0

    if 0 < score <= 1:
        score *= 100

    return max(0.0, min(100.0, score))


def skills_list(candidate: dict[str, Any]) -> list[str]:
    value = candidate.get("skills", [])

    if isinstance(value, dict):
        value = list(value.keys())

    return [
        str(item)
        for item in as_list(value)
        if str(item).strip()
    ]


def get_skill_list(
    data: dict[str, Any],
    keys: tuple[str, ...],
) -> list[str]:
    """Return normalized, case-insensitively unique skill strings."""
    value = first_value(data, keys, [])

    if isinstance(value, dict):
        value = list(value.keys())

    result = []
    seen = set()

    for item in as_list(value):
        if not isinstance(item, str) or not item.strip():
            continue

        skill = " ".join(item.split())
        normalized = skill.casefold()

        if normalized not in seen:
            seen.add(normalized)
            result.append(skill)

    return result


def unique_strings(values: Any) -> list[str]:
    """Normalize strings and remove case-insensitive duplicates."""
    result: list[str] = []
    seen: set[str] = set()

    for value in as_list(values):
        if not isinstance(value, str):
            continue

        item = " ".join(value.split()).strip()
        key = item.casefold()

        if item and key not in seen:
            seen.add(key)
            result.append(item)

    return result


def percent(value: Any) -> float | None:
    """Normalize score values to a 0–100 percentage."""
    if value is None:
        return None

    try:
        value = float(value)
    except (TypeError, ValueError):
        return None

    if 0 < value <= 1:
        value *= 100

    return max(0.0, min(100.0, value))


def get_percent(
    data: dict[str, Any],
    keys: tuple[str, ...],
) -> float | None:
    return percent(first_value(data, keys))


def candidate_key(candidate: dict[str, Any]) -> str:
    return str(
        candidate.get("filename")
        or candidate_name(candidate)
    ).casefold()


def clean_jd_limitation(value: Any) -> str:
    """Remove obsolete JD messages that conflict with the current workflow."""
    fallback = (
        "Skill detection uses a predefined dictionary and may miss unlisted "
        "skills or interpret context imperfectly. Detected mentions do not "
        "prove candidate proficiency or suitability."
    )

    if not isinstance(value, str) or not value.strip():
        return fallback

    message = value.strip()

    outdated_messages = [
        r"Skills are detected without assigning priority categories\.?",
        (
            r"The recruiter must choose Must-have,\s*Important,\s*"
            r"and Preferred skills before candidate scoring\.?"
        ),
    ]

    for pattern in outdated_messages:
        message = re.sub(
            pattern,
            "",
            message,
            flags=re.IGNORECASE,
        )

    message = re.sub(r"\s+", " ", message).strip(" \t\r\n;")

    return (
        message
        if message and re.search(r"[A-Za-z]", message)
        else fallback
    )


# ============================================================
# SKILL CATALOGUE AND ALIASES
# ============================================================

SKILL_CATALOG = [
    # Programming languages
    "Python", "Java", "C", "C++", "C#", "JavaScript",
    "TypeScript", "R", "Scala", "Go", "PHP", "Ruby",
    "Kotlin", "Swift",

    # AI and Machine Learning
    "Artificial Intelligence", "Machine Learning", "Deep Learning",
    "Generative AI", "Large Language Models", "LLM",
    "Prompt Engineering", "Neural Networks", "Supervised Learning",
    "Unsupervised Learning", "Reinforcement Learning", "Scikit-learn",
    "TensorFlow", "PyTorch", "Keras", "XGBoost", "LightGBM",
    "Model Training", "Model Evaluation", "Feature Engineering",
    "Feature Selection", "Hyperparameter Tuning", "Model Deployment",
    "Explainable AI",

    # Data Science and Analysis
    "Data Science", "Data Analysis", "Data Analytics",
    "Statistical Analysis", "Statistics", "Probability",
    "Data Cleaning", "Data Preprocessing", "Exploratory Data Analysis",
    "Data Visualization", "Predictive Modeling", "Time Series Analysis",
    "A/B Testing", "Pandas", "NumPy", "SciPy", "Matplotlib",
    "Seaborn", "Plotly",

    # NLP and semantic search
    "Natural Language Processing", "NLP", "Text Mining",
    "Text Classification", "Text Similarity", "Text Processing",
    "Information Extraction", "Named Entity Recognition",
    "Sentiment Analysis", "Tokenization", "TF-IDF",
    "Word Embeddings", "Semantic Embeddings", "Sentence Transformers",
    "Transformers", "Hugging Face", "BERT", "Cosine Similarity",
    "Vector Search", "Vector Databases",
    "Retrieval-Augmented Generation", "RAG",

    # Databases
    "SQL", "MySQL", "PostgreSQL", "SQLite", "MongoDB",
    "Microsoft SQL Server", "Oracle Database", "Database Design",
    "Database Management", "Data Modeling", "NoSQL",

    # Developer tools
    "Git", "GitHub", "GitLab", "Bitbucket", "Docker",
    "Kubernetes", "Linux", "Bash", "REST API", "API Development",
    "Postman",

    # Frameworks and web development
    "Flask", "FastAPI", "Django", "Streamlit", "Gradio",
    "React", "Node.js", "Express.js", "HTML", "CSS", "Bootstrap",

    # Cloud and deployment
    "AWS", "Microsoft Azure", "Google Cloud Platform",
    "Google Colab", "Jupyter Notebook", "CI/CD", "MLOps",
    "Model Monitoring", "Cloud Computing",

    # Software engineering
    "Object-Oriented Programming", "Data Structures", "Algorithms",
    "Software Engineering", "Software Testing", "Unit Testing",
    "Debugging", "Problem Solving", "System Design", "Agile", "Scrum",

    # BI and office tools
    "Microsoft Excel", "Advanced Excel", "Power BI", "Tableau",
    "Business Intelligence",
]

SKILL_ALIASES = {
    "ml": "Machine Learning",
    "ai": "Artificial Intelligence",
    "nlp": "Natural Language Processing",
    "sklearn": "Scikit-learn",
    "scikit learn": "Scikit-learn",
    "tf idf": "TF-IDF",
    "sentence transformer": "Sentence Transformers",
    "sentence-transformer": "Sentence Transformers",
    "fast api": "FastAPI",
    "nodejs": "Node.js",
    "powerbi": "Power BI",
    "postgres": "PostgreSQL",
    "huggingface": "Hugging Face",
    "llms": "Large Language Models",
}

# Extra option, separate from skills detected in the JD.
EXTRA_PRIORITY_OPTIONS = ["Data Structures"]


# ============================================================
# JOB DESCRIPTION SKILL DETECTION
# ============================================================

def _normalise_skill_text(value: str) -> str:
    """Normalize punctuation so variants such as TF-IDF and TF IDF match."""
    return " ".join(
        re.sub(r"[^a-z0-9]+", " ", str(value).casefold()).split()
    )


def _find_skill_match(raw_text: str, skill_variant: str):
    """Find an explicit skill mention in the supplied text."""
    compact = re.sub(r"\s+", "", skill_variant).casefold()

    if compact in {"c++", "c#"}:
        pattern = (
            r"(?<![A-Za-z0-9])"
            + re.escape(skill_variant.strip())
            + r"(?![A-Za-z0-9])"
        )
        return re.search(
            pattern,
            raw_text,
            flags=re.IGNORECASE,
        )

    normalized_variant = _normalise_skill_text(skill_variant)

    if (
        not normalized_variant
        or len(normalized_variant.replace(" ", "")) < 2
    ):
        return None

    tokens = normalized_variant.split()

    pattern = (
        r"(?<![A-Za-z0-9])"
        + r"[\W_]+".join(re.escape(token) for token in tokens)
        + r"(?![A-Za-z0-9])"
    )

    return re.search(
        pattern,
        raw_text,
        flags=re.IGNORECASE,
    )


def detect_skills_from_jd(
    job_description: str,
    analyzer_skills=None,
) -> list[str]:
    """
    Detect supported skills explicitly mentioned in the job description.

    Skills suggested by the JD analyzer are retained only when their
    canonical name or a supported alias is present in the JD text.
    """
    raw_text = str(job_description or "")
    detected: dict[str, str] = {}

    # Retain analyzer-provided skills only when the JD text supports them.
    for skill in as_list(analyzer_skills):
        if not isinstance(skill, str) or not skill.strip():
            continue

        cleaned = " ".join(skill.split())
        canonical = SKILL_ALIASES.get(
            cleaned.casefold(),
            cleaned,
        )

        variants = [cleaned, canonical]
        variants.extend(
            alias
            for alias, mapped in SKILL_ALIASES.items()
            if mapped.casefold() == canonical.casefold()
        )

        if any(
            _find_skill_match(raw_text, variant)
            for variant in variants
        ):
            detected[canonical.casefold()] = canonical

    # Match canonical catalogue skills explicitly present in the JD.
    for skill in SKILL_CATALOG:
        variants = [skill]
        variants.extend(
            alias
            for alias, canonical in SKILL_ALIASES.items()
            if canonical.casefold() == skill.casefold()
        )

        if any(
            _find_skill_match(raw_text, variant)
            for variant in variants
        ):
            canonical = SKILL_ALIASES.get(
                skill.casefold(),
                skill,
            )
            detected[canonical.casefold()] = canonical

    # Normalize explicit aliases such as NLP, TF-IDF, and FastAPI.
    for alias, canonical in SKILL_ALIASES.items():
        if _find_skill_match(raw_text, alias):
            detected[canonical.casefold()] = canonical

    return sorted(
        detected.values(),
        key=str.casefold,
    )


# ============================================================
# RESUME-TEXT SKILL MATCHING
# ============================================================

def enrich_candidates_from_resume_text(
    candidates: list[dict[str, Any]],
    job_skills: list[str],
) -> list[dict[str, Any]]:
    """Add explicit JD skill mentions found in extracted resume text."""
    canonical_skills = unique_strings(job_skills)

    alias_variants: dict[str, list[str]] = {}

    for alias, canonical in SKILL_ALIASES.items():
        alias_variants.setdefault(
            canonical.casefold(),
            [],
        ).append(alias)

    output: list[dict[str, Any]] = []

    for original in candidates:
        if not isinstance(original, dict):
            continue

        candidate = dict(original)

        raw_text = first_value(
            candidate,
            (
                "text",
                "full_text",
                "extracted_text",
                "raw_text",
                "content",
                "resume_text",
                "resume_content",
            ),
            "",
        )

        if not isinstance(raw_text, str) or not raw_text.strip():
            output.append(candidate)
            continue

        existing_skills = skills_list(candidate)
        existing_keys = {
            item.casefold()
            for item in existing_skills
        }

        evidence = candidate.get("skill_evidence", {})

        if not isinstance(evidence, dict):
            evidence = {}

        evidence = dict(evidence)

        evidence_keys = {
            str(key).casefold(): key
            for key in evidence
        }

        for skill in canonical_skills:
            variants = (
                [skill]
                + alias_variants.get(skill.casefold(), [])
            )

            match = None

            for variant in variants:
                match = _find_skill_match(raw_text, variant)
                if match is not None:
                    break

            if match is None:
                continue

            if skill.casefold() not in existing_keys:
                existing_skills.append(skill)
                existing_keys.add(skill.casefold())

            start = max(0, match.start() - 90)
            end = min(len(raw_text), match.end() + 90)

            snippet = " ".join(
                raw_text[start:end].split()
            )

            evidence_key = evidence_keys.get(
                skill.casefold(),
                skill,
            )

            items = evidence.get(evidence_key, [])

            if isinstance(items, (str, dict)):
                items = [items]
            elif not isinstance(items, list):
                items = []

            already_present = any(
                isinstance(item, dict)
                and str(item.get("snippet", "")).strip() == snippet
                for item in items
            )

            if not already_present:
                items.append({
                    "matched_text": match.group(0),
                    "snippet": snippet,
                    "source": "extracted_resume_text",
                })

                evidence[evidence_key] = items
                evidence_keys[skill.casefold()] = evidence_key

        candidate["skills"] = unique_strings(existing_skills)
        candidate["skill_evidence"] = evidence
        output.append(candidate)

    return output


# ============================================================
# EVIDENCE DISPLAY
# ============================================================

def render_evidence(candidate: dict[str, Any]) -> None:
    st.markdown("#### Resume Evidence Verification")

    evidence = candidate.get("skill_evidence", {})

    if not isinstance(evidence, dict) or not evidence:
        st.info(
            "No skill evidence snippets were returned for this candidate."
        )
        return

    shown = 0
    snippet_count = 0

    for skill, items in evidence.items():
        if isinstance(items, (str, dict)):
            items = [items]

        if not isinstance(items, (list, tuple)):
            continue

        clean = []

        for item in items:
            if isinstance(item, dict):
                snippet = item.get("snippet", "")
                matched = item.get("matched_text", "")
            else:
                snippet = str(item or "")
                matched = ""

            if isinstance(snippet, str) and snippet.strip():
                clean.append((
                    snippet.strip(),
                    matched.strip() if isinstance(matched, str) else "",
                ))

        if clean:
            with st.expander(
                f"{skill} — {len(clean)} evidence snippet(s)"
            ):
                for snippet, matched in clean:
                    if matched:
                        st.caption(f"Detected text: {matched}")

                    st.write(f"“{snippet}”")

            shown += 1
            snippet_count += len(clean)

    if shown:
        st.success(
            f"Evidence found for {shown} skill(s), "
            f"with {snippet_count} snippet(s)."
        )
    else:
        st.info("No usable evidence snippets were found.")

    st.caption(
        "Evidence snippets show text found in a resume. "
        "They do not prove proficiency or document authenticity."
    )


# ============================================================
# EXPORT DATAFRAME
# ============================================================

def results_dataframe(
    candidates: list[dict[str, Any]],
) -> pd.DataFrame:
    rows = []

    for candidate in candidates:
        rows.append({
            "Rank": candidate.get("rank", ""),
            "Candidate": candidate_name(candidate),
            "Filename": candidate.get("filename", ""),
            "Email": candidate.get("email", ""),
            "Phone": candidate.get("phone", ""),
            "Final Score (%)": round(candidate_score(candidate), 2),
            "Decision": first_value(
                candidate,
                (
                    "decision",
                    "status",
                    "shortlisting_status",
                    "shortlist_status",
                ),
                (
                    "Shortlisted"
                    if candidate.get(
                        "shortlisted",
                        candidate.get("eligible", False),
                    )
                    else "Review required"
                ),
            ),
            "Shortlisted": candidate.get(
                "shortlisted",
                candidate.get("eligible", False),
            ),
            "Must-have Coverage (%)": get_percent(
                candidate,
                (
                    "must_have_coverage",
                    "must_have_coverage_pct",
                    "must_have_score",
                ),
            ),
            "Shortlisting Reasons": "; ".join(
                unique_strings(
                    first_value(
                        candidate,
                        (
                            "shortlisting_reasons",
                            "rejection_reasons",
                            "reasons",
                        ),
                        [],
                    )
                )
            ),
            "Matched Skills": ", ".join(
                get_skill_list(
                    candidate,
                    (
                        "full_jd_matched_skills",
                        "matched_skills",
                        "skills_matched",
                    ),
                )
            ),
            "Missing Skills": ", ".join(
                get_skill_list(
                    candidate,
                    (
                        "full_jd_missing_skills",
                        "missing_skills",
                        "skills_missing",
                    ),
                )
            ),
            "All Detected Skills": ", ".join(
                skills_list(candidate)
            ),
            "Education": as_text(candidate.get("education")),
            "Experience": as_text(candidate.get("experience")),
            "Projects": as_text(candidate.get("projects")),
            "Certifications": as_text(
                candidate.get("certifications")
            ),
        })

    return pd.DataFrame(rows)


# ============================================================
# SIDEBAR SETTINGS
# ============================================================

with st.sidebar:
    st.title("⚙️ Screening Settings")
    st.caption("Configure matching and shortlisting criteria.")

    score_min = st.slider(
        "Minimum overall score (%)",
        min_value=0,
        max_value=100,
        value=70,
        step=5,
    )

    must_min = st.slider(
        "Minimum must-have coverage (%)",
        min_value=0,
        max_value=100,
        value=80,
        step=5,
    )

    st.divider()

    use_semantic = st.checkbox(
        "Enable semantic matching",
        value=True,
    )

    semantic_weight_pct = st.slider(
        "Semantic score weight (%)",
        min_value=0,
        max_value=100,
        value=30,
        step=5,
        disabled=not use_semantic,
    )

    st.divider()
    st.markdown("#### Skill Category Weights")

    must_weight = st.number_input(
        "Must-have weight (%)",
        min_value=0,
        max_value=100,
        value=50,
        step=5,
    )

    important_weight = st.number_input(
        "Important weight (%)",
        min_value=0,
        max_value=100,
        value=30,
        step=5,
    )

    preferred_weight = st.number_input(
        "Preferred weight (%)",
        min_value=0,
        max_value=100,
        value=20,
        step=5,
    )

    weight_total = (
        must_weight
        + important_weight
        + preferred_weight
    )

    if weight_total != 100:
        st.warning(
            f"Category weights total {weight_total}%. "
            "They must total exactly 100%."
        )

    st.divider()

    if st.button(
        "🧹 Clear Previous Results",
        use_container_width=True,
    ):
        for key in list(st.session_state.keys()):
            if key.startswith("priority_choice_"):
                del st.session_state[key]

        for key in (
            "must_have_selection",
            "important_selection",
            "preferred_selection",
        ):
            if key in st.session_state:
                del st.session_state[key]

        for key, value in DEFAULT_STATE.items():
            st.session_state[key] = value

        st.rerun()


# ============================================================
# APPLICATION HEADER
# ============================================================

st.title("📄 AI-Based Resume Shortlisting")

st.markdown(
    """
    **AI-powered resume screening and candidate matching**

    Paste a job description and upload PDF/DOCX resumes to compare
    skill coverage, review evidence, rank candidates, and prepare
    a shortlist.
    """
)

# The large yellow human-review warning banner has been removed.


# ============================================================
# INPUTS
# ============================================================

st.subheader("1. Job Description")

job_description = st.text_area(
    "Paste the complete job description",
    value=st.session_state.get("job_description", ""),
    height=220,
    placeholder=(
        "Include responsibilities, required skills, education, "
        "experience, and preferred qualifications."
    ),
    key="job_description_input",
)

st.subheader("2. Upload Resumes")

uploads = st.file_uploader(
    "Upload multiple PDF or DOCX resumes",
    type=["pdf", "docx"],
    accept_multiple_files=True,
)

valid_uploads = [
    file
    for file in (uploads or [])
    if file.name.lower().endswith((".pdf", ".docx"))
]

if uploads:
    st.caption(
        f"{len(valid_uploads)} supported resume file(s) selected."
    )

    with st.expander("View Uploaded Filenames"):
        for file in valid_uploads:
            st.write(f"📄 {file.name}")


# ============================================================
# PHASE 1: ANALYSE RESUMES AND JOB DESCRIPTION
# ============================================================

if st.button(
    "🔎 Analyse Resumes & Detect Skills",
    type="primary",
    use_container_width=True,
):
    # Reset analysis and priority selections for a new job.
    for key in list(st.session_state.keys()):
        if key.startswith("priority_choice_"):
            del st.session_state[key]

    for key in (
        "must_have_selection",
        "important_selection",
        "preferred_selection",
    ):
        if key in st.session_state:
            del st.session_state[key]

    for key, value in DEFAULT_STATE.items():
        st.session_state[key] = value

    if not job_description.strip():
        st.error("Please enter a job description first.")

    elif not valid_uploads:
        st.error(
            "Please upload at least one supported PDF or DOCX resume."
        )

    else:
        progress = st.progress(0)
        status = st.empty()

        analysed: list[dict[str, Any]] = []
        failed: list[dict[str, str]] = []

        for index, uploaded in enumerate(
            valid_uploads,
            start=1,
        ):
            status.write(
                f"Reading resume {index}/{len(valid_uploads)}: "
                f"{uploaded.name}"
            )

            temp_path = None

            try:
                suffix = Path(uploaded.name).suffix.lower()

                with tempfile.NamedTemporaryFile(
                    delete=False,
                    suffix=suffix,
                ) as temp:
                    temp.write(uploaded.getvalue())
                    temp_path = temp.name

                data = analyze_resume(temp_path)

                if not isinstance(data, dict):
                    raise TypeError(
                        "analyze_resume() did not return a dictionary."
                    )

                data = dict(data)
                data["filename"] = uploaded.name

                # Preserve an extracted name; otherwise use filename.
                if not data.get("candidate_name"):
                    data["candidate_name"] = Path(
                        uploaded.name
                    ).stem

                analysed.append(data)

            except Exception as exc:
                failed.append({
                    "filename": uploaded.name,
                    "error": str(exc),
                })

            finally:
                if temp_path:
                    try:
                        Path(temp_path).unlink(missing_ok=True)
                    except OSError:
                        pass

            progress.progress(index / len(valid_uploads))

        progress.empty()
        status.empty()

        if failed:
            with st.expander(
                f"⚠️ {len(failed)} file(s) could not be analysed",
                expanded=True,
            ):
                for item in failed:
                    st.write(f"**{item['filename']}**")
                    st.caption(item["error"])

        if not analysed:
            st.error(
                "No resumes could be analysed. "
                "Check the parser and uploaded files."
            )

        else:
            try:
                with st.spinner(
                    "Analysing job description and detecting skills..."
                ):
                    jd = analyze_job_description(job_description)

                if not isinstance(jd, dict):
                    raise TypeError(
                        "analyze_job_description() must return a dictionary."
                    )

                # Only skills explicitly found in JD text are detected.
                analyzer_skills = get_skill_list(
                    jd,
                    ("skills", "all_skills", "required_skills"),
                )

                detected = detect_skills_from_jd(
                    job_description,
                    analyzer_skills,
                )

                if not detected:
                    raise ValueError(
                        "No recognized skills were found in the job "
                        "description. Check the JD and the supported "
                        "skill detection catalogue."
                    )

                jd["skills"] = detected
                jd["detected_skills"] = detected.copy()
                jd["must_have_skills"] = []
                jd["important_skills"] = []
                jd["preferred_skills"] = []

                st.session_state.update({
                    "analysed_candidates": analysed,
                    "job_analysis": jd,
                    "job_description": job_description,
                    "analysis_ready": True,
                    "analysis_complete": False,
                    "priority_selections": {},
                    "ranked_candidates": [],
                    "final_candidates": [],
                    "analysis_settings": {
                        "semantic_enabled": use_semantic,
                        "semantic_weight": semantic_weight_pct,
                        "score_threshold": score_min,
                        "must_have_threshold": must_min,
                        "weights": {
                            "must_have": float(must_weight) / 100,
                            "important": float(important_weight) / 100,
                            "preferred": float(preferred_weight) / 100,
                        },
                    },
                })

                st.success(
                    f"Analysed {len(analysed)} resume(s). "
                    f"Detected {len(detected)} job skill(s). "
                    "Now assign priorities below."
                )

            except Exception as exc:
                st.session_state["analysis_ready"] = False
                st.error("The analysis pipeline encountered an error.")
                st.exception(exc)


# ============================================================
# PHASE 2: RECRUITER SKILL PRIORITY SELECTION
# ============================================================

if (
    st.session_state.get("analysis_ready")
    and not st.session_state.get("analysis_complete")
):
    jd_for_selection = st.session_state["job_analysis"] or {}

    detected_skills = get_skill_list(
        jd_for_selection,
        ("detected_skills", "skills"),
    )

    def _unique_skills(items):
        output = []
        seen = set()

        for item in items:
            if not isinstance(item, str):
                continue

            cleaned = item.strip()
            key = cleaned.casefold()

            if cleaned and key not in seen:
                seen.add(key)
                output.append(cleaned)

        return output

    st.divider()
    st.header("3. Recruiter Skill Priority Selection")

    st.write(
        "Assign the detected skills to Must-have, Important, "
        "or Preferred. A skill can be assigned to only one category."
    )

    st.info(
        "Skill detection identifies mentions in the job description. "
        "You decide which skills are essential for this role."
    )

    skill_options = _unique_skills(
        detected_skills + EXTRA_PRIORITY_OPTIONS
    )

    valid_option_keys = {
        item.casefold()
        for item in skill_options
    }

    used_skill_keys = set()

    for selection_key in (
        "must_have_selection",
        "important_selection",
        "preferred_selection",
    ):
        cleaned_selection = []

        for skill in st.session_state.get(selection_key, []):
            normalized_skill = str(skill).casefold()

            if (
                normalized_skill in valid_option_keys
                and normalized_skill not in used_skill_keys
            ):
                cleaned_selection.append(skill)
                used_skill_keys.add(normalized_skill)

        st.session_state[selection_key] = cleaned_selection

    must_selected_keys = {
        str(item).casefold()
        for item in st.session_state.get(
            "must_have_selection",
            [],
        )
    }

    important_selected_keys = {
        str(item).casefold()
        for item in st.session_state.get(
            "important_selection",
            [],
        )
    }

    preferred_selected_keys = {
        str(item).casefold()
        for item in st.session_state.get(
            "preferred_selection",
            [],
        )
    }

    must_options = [
        item
        for item in skill_options
        if item.casefold()
        not in important_selected_keys | preferred_selected_keys
    ]

    important_options = [
        item
        for item in skill_options
        if item.casefold()
        not in must_selected_keys | preferred_selected_keys
    ]

    preferred_options = [
        item
        for item in skill_options
        if item.casefold()
        not in must_selected_keys | important_selected_keys
    ]

    col1, col2, col3 = st.columns(3)

    with col1:
        st.subheader("🔴 Must-have")

        must_have = st.multiselect(
            "Select Must-have skills",
            options=must_options,
            key="must_have_selection",
            placeholder="Search essential skills...",
            help="Skills assigned to other categories are hidden here.",
        )

    with col2:
        st.subheader("🟠 Important")

        important = st.multiselect(
            "Select Important skills",
            options=important_options,
            key="important_selection",
            placeholder="Search important skills...",
            help="Skills assigned to other categories are hidden here.",
        )

    with col3:
        st.subheader("🟢 Preferred")

        preferred = st.multiselect(
            "Select Preferred skills",
            options=preferred_options,
            key="preferred_selection",
            placeholder="Search preferred skills...",
            help="Skills assigned to other categories are hidden here.",
        )

    all_selected = must_have + important + preferred
    selected_keys = [item.casefold() for item in all_selected]
    duplicates_exist = len(selected_keys) != len(set(selected_keys))

    st.divider()
    st.subheader("Selected Skills Summary")

    summary1, summary2, summary3 = st.columns(3)

    summary1.metric("Must-have", len(must_have))
    summary2.metric("Important", len(important))
    summary3.metric("Preferred", len(preferred))

    if duplicates_exist:
        st.error(
            "A skill can belong to only one category. "
            "Remove duplicate selections."
        )

    selected_key_set = set(selected_keys)

    unassigned = [
        item
        for item in skill_options
        if item.casefold() not in selected_key_set
    ]

    with st.expander(f"Unassigned Skills ({len(unassigned)})"):
        st.write(
            ", ".join(unassigned)
            if unassigned
            else "All available skills are assigned."
        )

    if st.button(
        "🏆 Run Shortlist Using My Priorities",
        type="primary",
        use_container_width=True,
    ):
        if not must_have:
            st.error("Please select at least one Must-have skill.")

        elif weight_total != 100:
            st.error(
                "The three category weights must total exactly 100%."
            )

        elif duplicates_exist:
            st.error(
                "Each skill must be assigned to only one category."
            )

        else:
            try:
                selected = {
                    "must_have": must_have,
                    "important": important,
                    "preferred": preferred,
                }

                priorities = configure_candidate_priorities(selected)

                configured_jd = dict(jd_for_selection)

                configured_jd["must_have_skills"] = priorities["must_have"]
                configured_jd["important_skills"] = priorities["important"]
                configured_jd["preferred_skills"] = priorities["preferred"]

                weights = {
                    "must_have": float(must_weight) / 100,
                    "important": float(important_weight) / 100,
                    "preferred": float(preferred_weight) / 100,
                }

                # Detected JD skills and extra priority skills are
                # kept separate for accurate display.
                matching_skills = _unique_skills(
                    detected_skills + all_selected
                )

                configured_jd["detected_skills"] = detected_skills.copy()

                configured_jd["additional_priority_skills"] = [
                    skill
                    for skill in all_selected
                    if skill.casefold()
                    not in {
                        item.casefold()
                        for item in detected_skills
                    }
                ]

                configured_jd["skills"] = matching_skills

                analysed = enrich_candidates_from_resume_text(
                    st.session_state["analysed_candidates"],
                    matching_skills,
                )

                st.session_state["analysed_candidates"] = analysed
                jd_text = st.session_state["job_description"]

                with st.spinner("Ranking candidates..."):
                    ranked = rank_candidates(
                        analysed,
                        configured_jd,
                        use_semantic=use_semantic,
                        job_description=jd_text,
                        semantic_weight=(
                            semantic_weight_pct / 100
                            if use_semantic
                            else 0.0
                        ),
                    )

                with st.spinner("Preparing shortlist..."):
                    final = shortlist_candidates(
                        ranked,
                        priorities,
                        weights=weights,
                        score_threshold=float(score_min),
                        min_must_have_coverage=float(must_min),
                        job_skills=matching_skills,
                        use_semantic=use_semantic,
                        semantic_weight=(
                            semantic_weight_pct / 100
                            if use_semantic
                            else 0.0
                        ),
                        skill_alternatives=configured_jd.get(
                            "skill_alternatives"
                        ),
                    )

                st.session_state["ranked_candidates"] = ranked
                st.session_state["final_candidates"] = final
                st.session_state["job_analysis"] = configured_jd
                st.session_state["analysis_complete"] = True
                st.session_state["priority_selections"] = priorities

                st.session_state["analysis_settings"] = {
                    "semantic_enabled": use_semantic,
                    "semantic_weight": semantic_weight_pct,
                    "score_threshold": score_min,
                    "must_have_threshold": must_min,
                    "weights": weights,
                    "priorities": priorities,
                }

                st.success("Shortlist generated successfully!")
                st.rerun()

            except Exception as exc:
                st.error("Could not generate the shortlist.")
                st.exception(exc)


# ============================================================
# PHASE 3: RESULTS DASHBOARD
# ============================================================

if st.session_state.get("analysis_complete"):
    ranked = st.session_state["ranked_candidates"]
    final = st.session_state["final_candidates"]
    jd = st.session_state["job_analysis"] or {}
    settings = st.session_state["analysis_settings"]

    # Keep displayed scores and ranking tied to final shortlisting results.
    display_candidates = final if final else ranked

    if not display_candidates:
        st.info("No ranked candidates were returned.")
        st.stop()

    st.divider()
    st.header("📊 Screening Results")

    shortlisted = [
        candidate
        for candidate in display_candidates
        if candidate.get(
            "shortlisted",
            candidate.get("eligible", False),
        )
    ]

    display_scores = [
        candidate_score(candidate)
        for candidate in display_candidates
    ]

    analysed_count = len(
        st.session_state.get("analysed_candidates", [])
    )

    cols = st.columns(4)

    cols[0].metric(
        "Resumes analysed",
        analysed_count if analysed_count else len(display_candidates),
    )

    cols[1].metric("Shortlisted", len(shortlisted))

    cols[2].metric(
        "Review required",
        max(0, len(display_candidates) - len(shortlisted)),
    )

    cols[3].metric(
        "Average score",
        (
            f"{sum(display_scores) / len(display_scores):.2f}%"
            if display_scores
            else "N/A"
        ),
        help=(
            "Average of the same final scores displayed in the "
            "ranking table and candidate detail cards."
        ),
    )

    # --------------------------------------------------------
    # ANALYSIS SETTINGS
    # --------------------------------------------------------

    with st.expander("View Analysis Settings"):
        st.write(
            "**Semantic matching:** "
            + (
                "Enabled"
                if settings.get("semantic_enabled")
                else "Disabled"
            )
        )

        st.write(
            f"**Semantic weight:** "
            f"{settings.get('semantic_weight', 0)}%"
        )

        st.write(
            f"**Minimum overall score:** "
            f"{settings.get('score_threshold', 0)}%"
        )

        st.write(
            f"**Minimum must-have coverage:** "
            f"{settings.get('must_have_threshold', 0)}%"
        )

        st.write("**Category weights:**")
        st.json(settings.get("weights", {}))

        st.write("**Configured skill priorities:**")
        st.json(settings.get("priorities", {}))

    # --------------------------------------------------------
    # CANDIDATE RANKING TABLE
    # --------------------------------------------------------

    st.subheader("🏆 Candidate Ranking")

    ranking_rows = []

    for index, candidate in enumerate(display_candidates, start=1):
        is_shortlisted = bool(
            candidate.get(
                "shortlisted",
                candidate.get("eligible", False),
            )
        )

        decision = first_value(
            candidate,
            (
                "decision",
                "status",
                "shortlisting_status",
                "shortlist_status",
            ),
            (
                "Shortlisted"
                if is_shortlisted
                else "Review required"
            ),
        )

        ranking_rows.append({
            "Rank": candidate.get("rank", index),
            "Candidate": candidate_name(candidate),
            "Score (%)": round(candidate_score(candidate), 2),
            "Decision": decision,
            "Email": candidate.get("email", ""),
            "Filename": candidate.get("filename", ""),
            "Must-have Coverage (%)": get_percent(
                candidate,
                (
                    "must_have_coverage",
                    "must_have_coverage_pct",
                    "must_have_score",
                ),
            ),
            "Missing Must-have Skills": ", ".join(
                get_skill_list(
                    candidate,
                    (
                        "missing_must_have_skills",
                        "must_have_missing_skills",
                    ),
                )
            ),
        })

    ranking_df = pd.DataFrame(ranking_rows)

    st.caption(
        f"Showing {len(ranking_df)} candidate(s). "
        "Scores match the summary and detail cards."
    )

    st.dataframe(
        ranking_df,
        use_container_width=True,
        hide_index=True,
    )

    st.download_button(
        "⬇️ Download Ranking CSV",
        ranking_df.to_csv(index=False).encode("utf-8-sig"),
        "candidate_ranking.csv",
        "text/csv",
        use_container_width=True,
    )

    # --------------------------------------------------------
    # JOB DESCRIPTION SUMMARY
    # --------------------------------------------------------

    st.subheader("🧾 Job Description Summary")

    actually_detected = get_skill_list(
        jd,
        ("detected_skills", "skills"),
    )

    st.write(
        "**Detected skills in job description:**",
        as_text(actually_detected),
    )

    additional_priority_skills = get_skill_list(
        jd,
        ("additional_priority_skills",),
    )

    if additional_priority_skills:
        st.write(
            "**Additional recruiter-selected skills:**",
            as_text(additional_priority_skills),
        )

    p1, p2, p3 = st.columns(3)

    p1.markdown("**Must-have skills**")
    p1.write(as_text(jd.get("must_have_skills", [])))

    p2.markdown("**Important skills**")
    p2.write(as_text(jd.get("important_skills", [])))

    p3.markdown("**Preferred skills**")
    p3.write(as_text(jd.get("preferred_skills", [])))

    jd_limitation = clean_jd_limitation(jd.get("limitation"))

    if jd_limitation:
        st.info(jd_limitation)

    # --------------------------------------------------------
    # CANDIDATE DETAILS
    # --------------------------------------------------------

    st.subheader("🔍 Candidate Details")

    for index, candidate in enumerate(display_candidates, start=1):
        name = candidate_name(candidate)
        score = candidate_score(candidate)

        is_shortlisted = bool(
            candidate.get(
                "shortlisted",
                candidate.get("eligible", False),
            )
        )

        decision = first_value(
            candidate,
            (
                "decision",
                "status",
                "shortlisting_status",
                "shortlist_status",
            ),
            (
                "Shortlisted"
                if is_shortlisted
                else "Review required"
            ),
        )

        with st.expander(
            f"{candidate.get('rank', index)}. {name} — "
            f"{score:.2f}% — {decision}",
            expanded=index == 1,
        ):
            col1, col2, col3 = st.columns(3)

            col1.metric("Overall Score", f"{score:.2f}%")

            if is_shortlisted:
                col2.success("Meets current shortlist criteria")
            else:
                col2.warning(
                    "Requires review against current criteria"
                )

            coverage = get_percent(
                candidate,
                (
                    "must_have_coverage",
                    "must_have_coverage_pct",
                    "must_have_score",
                ),
            )

            col3.metric(
                "Must-have Coverage",
                (
                    f"{coverage:.2f}%"
                    if coverage is not None
                    else "Not available"
                ),
            )

            # -----------------------------------------------
            # SHORTLISTING CRITERIA CHECK
            # -----------------------------------------------

            st.markdown("#### Shortlisting Criteria Check")

            backend_reasons = unique_strings(
                first_value(
                    candidate,
                    (
                        "shortlisting_reasons",
                        "rejection_reasons",
                        "reasons",
                    ),
                    [],
                )
            )

            if not is_shortlisted:
                if backend_reasons:
                    for reason in backend_reasons:
                        st.warning(reason)

                else:
                    threshold_reasons = []

                    overall_threshold = float(
                        settings.get("score_threshold", 0)
                    )

                    coverage_threshold = float(
                        settings.get("must_have_threshold", 0)
                    )

                    if score < overall_threshold:
                        threshold_reasons.append(
                            f"Overall score {score:.2f}% is below "
                            f"the required {overall_threshold:.2f}%."
                        )

                    if coverage is not None:
                        if coverage < coverage_threshold:
                            threshold_reasons.append(
                                f"Must-have coverage {coverage:.2f}% "
                                f"is below the required "
                                f"{coverage_threshold:.2f}%."
                            )
                    else:
                        threshold_reasons.append(
                            "Must-have coverage was not returned "
                            "by the scoring engine."
                        )

                    if threshold_reasons:
                        for reason in threshold_reasons:
                            st.warning(reason)

                    else:
                        st.info(
                            "The backend marked this candidate as "
                            "not shortlisted, but no specific reason "
                            "was returned. Check additional eligibility "
                            "rules in services/shortlisting_engine.py."
                        )

            else:
                positive_reasons = [
                    reason
                    for reason in backend_reasons
                    if not any(
                        phrase in reason.casefold()
                        for phrase in (
                            "below the required",
                            "not shortlisted",
                            "no must-have skills",
                            "failed",
                            "ineligible",
                        )
                    )
                ]

                if positive_reasons:
                    for reason in positive_reasons:
                        st.success(reason)
                else:
                    st.success(
                        "The candidate passed the configured "
                        "shortlisting decision."
                    )

            # -----------------------------------------------
            # CANDIDATE PROFILE
            # -----------------------------------------------

            st.markdown("#### Candidate Profile")

            left, right = st.columns(2)

            left.write(
                f"**Email:** {as_text(candidate.get('email'))}"
            )

            left.write(
                f"**Phone:** {as_text(candidate.get('phone'))}"
            )

            left.write(
                f"**Education:** {as_text(candidate.get('education'))}"
            )

            right.write(
                f"**Experience:** {as_text(candidate.get('experience'))}"
            )

            right.write(
                f"**Projects:** {as_text(candidate.get('projects'))}"
            )

            right.write(
                f"**Certifications:** "
                f"{as_text(candidate.get('certifications'))}"
            )

            # -----------------------------------------------
            # SCORE BREAKDOWN
            # -----------------------------------------------

            st.markdown("#### Score Breakdown")

            score_fields = [
                ("Priority Skill Score", ("priority_skill_score",)),
                ("Semantic Score", ("semantic_score",)),
                ("TF-IDF Score", ("tfidf_score", "tf_idf_score")),
            ]

            score_values = [
                (label, value)
                for label, keys in score_fields
                if (
                    value := get_percent(candidate, keys)
                ) is not None
            ]

            if score_values:
                score_cols = st.columns(len(score_values))

                for col, (label, value) in zip(
                    score_cols,
                    score_values,
                ):
                    col.metric(label, f"{value:.2f}%")

            else:
                st.info(
                    "Separate score components were not returned "
                    "by the ranking engine."
                )

            # -----------------------------------------------
            # MATCHED AND MISSING SKILLS
            # -----------------------------------------------

            st.markdown("#### Matched and Missing Skills")

            matched = get_skill_list(
                candidate,
                (
                    "full_jd_matched_skills",
                    "matched_skills",
                    "skills_matched",
                ),
            )

            missing = get_skill_list(
                candidate,
                (
                    "full_jd_missing_skills",
                    "missing_skills",
                    "skills_missing",
                ),
            )

            left, right = st.columns(2)

            left.markdown("**Matched Skills**")

            if matched:
                for skill in matched:
                    left.write(f"✅ {skill}")
            else:
                left.write("No matched-skill list available.")

            right.markdown("**Missing Skills**")

            if missing:
                for skill in missing:
                    right.write(f"⚠️ {skill}")
            else:
                right.write("No missing-skill list available.")

            # -----------------------------------------------
            # DETECTED RESUME SKILLS
            # -----------------------------------------------

            st.markdown("#### Detected Resume Skills")

            st.write(
                ", ".join(skills_list(candidate))
                or "No detected skills were returned."
            )

            render_evidence(candidate)

            # -----------------------------------------------
            # RESUME EXTRACTION NOTES
            # -----------------------------------------------

            limitation = first_value(
                candidate,
                (
                    "limitation",
                    "resume_extraction_limitation",
                    "extraction_warning",
                ),
            )

            if limitation:
                limitation_text = str(limitation)

                if (
                    "baseline compares skill names only"
                    in limitation_text.casefold()
                ):
                    st.info(
                        "Skill extraction note: Skills are detected "
                        "from extracted resume text, but the parser "
                        "may miss aliases or context and does not verify "
                        "proficiency or years of experience. Explicit "
                        "mentions found in the extracted text are also "
                        "checked for job-skill matching. Semantic "
                        "similarity, when enabled, contributes separately "
                        "to the overall score. The score is not a "
                        "probability of hiring success."
                    )
                else:
                    st.info(
                        f"Resume extraction note: {limitation_text}"
                    )

            # -----------------------------------------------
            # EXTRACTED RESUME TEXT
            # -----------------------------------------------

            resume_text = first_value(
                candidate,
                (
                    "text",
                    "full_text",
                    "extracted_text",
                    "raw_text",
                    "content",
                    "resume_text",
                    "resume_content",
                ),
                "",
            )

            if isinstance(resume_text, str) and resume_text.strip():
                with st.expander("View Extracted Resume Text"):
                    st.text(resume_text)

    # --------------------------------------------------------
    # EXPORT RESULTS
    # --------------------------------------------------------

    st.divider()
    st.subheader("📥 Export Results")

    report_df = results_dataframe(display_candidates)

    st.download_button(
        "⬇️ Download Complete Screening Report (CSV)",
        report_df.to_csv(index=False).encode("utf-8-sig"),
        "resume_screening_report.csv",
        "text/csv",
        use_container_width=True,
    )

    st.caption(
        "Exports contain candidate data and screening scores. "
        "Store and share candidate information securely."
    )


# ============================================================
# FOOTER
# ============================================================

st.divider()

st.caption(
    "AI-Based Resume Shortlisting | NLP + Skill Matching + "
    "Semantic Matching | Automated screening support"
)