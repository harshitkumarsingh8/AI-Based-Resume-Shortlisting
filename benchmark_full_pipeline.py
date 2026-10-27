from pathlib import Path
from time import perf_counter
import csv
import traceback

from services.resume_analyzer import analyze_resume
from services.jd_analyzer import analyze_job_description
from services.candidate_ranker import rank_candidates
from services.shortlisting_engine import (
    configure_candidate_priorities,
    shortlist_candidates,
)


# ============================================================
# CONFIGURATION
# ============================================================

PROJECT_DIR = Path(__file__).resolve().parent
RESUME_DIR = PROJECT_DIR / "benchmark_resumes"
REPORT_PATH = PROJECT_DIR / "benchmark_full_pipeline_report.csv"

JOB_DESCRIPTION = """
AI/ML Intern

Responsibilities:
- Develop and evaluate machine learning models.
- Process datasets using Python, Pandas and NumPy.
- Apply machine learning and deep learning techniques.
- Work with SQL databases.
- Build basic AI applications and prototypes.
- Use Git for version control.

Required skills:
Python, Machine Learning, Deep Learning

Preferred skills:
SQL, Pandas, NumPy, Artificial Intelligence, Git, Streamlit
"""

PRIORITIES = {
    "must_have": [
        "Python",
        "Machine Learning",
        "Deep Learning",
    ],
    "important": [
        "SQL",
        "Pandas",
        "NumPy",
        "Artificial Intelligence",
    ],
    "preferred": [
        "Git",
        "Streamlit",
    ],
}

CATEGORY_WEIGHTS = {
    "must_have": 0.50,
    "important": 0.30,
    "preferred": 0.20,
}

SCORE_THRESHOLD = 70
MUST_HAVE_THRESHOLD = 80

# Semantic matching is disabled for this repeatable benchmark.
USE_SEMANTIC = False
SEMANTIC_WEIGHT = 0.0


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def get_skills(data):
    """Safely read the skills field from a dictionary."""

    if not isinstance(data, dict):
        return []

    skills = data.get("skills", [])

    if isinstance(skills, str):
        skills = [skills]

    if not isinstance(skills, (list, tuple, set)):
        return []

    cleaned_skills = []

    for skill in skills:
        skill = str(skill).strip()

        if skill and skill not in cleaned_skills:
            cleaned_skills.append(skill)

    return cleaned_skills


def get_score(candidate):
    """Return a valid candidate score between 0 and 100."""

    score_fields = (
        "shortlisting_score",
        "match_score",
        "final_score",
        "overall_score",
        "score",
    )

    for field in score_fields:
        value = candidate.get(field)

        try:
            if value is not None:
                score = float(value)

                if 0 <= score <= 100:
                    return round(score, 2)

        except (TypeError, ValueError):
            continue

    return None


def readable(value):
    """Convert lists and other values into readable CSV text."""

    if value is None:
        return ""

    if isinstance(value, (list, tuple, set)):
        return "; ".join(str(item) for item in value)

    return str(value)


def get_candidate_name(candidate, filename):
    """
    Preserve the extracted name when available.
    Use the filename if the extracted name is blank.
    """

    name = candidate.get("name")

    if name is not None:
        name = str(name).strip()
    else:
        name = ""

    if name:
        return name

    # Fallback example: synthetic_resume_001
    return Path(filename).stem


def get_shortlisted_count(rows):
    """Count candidates whose shortlisted status is truthy."""

    count = 0

    for row in rows:
        value = str(row.get("shortlisted", "")).strip().lower()

        if value in {"true", "1", "yes"}:
            count += 1

    return count


# ============================================================
# MAIN BENCHMARK
# ============================================================

def main():
    print("=" * 65)
    print("AI RESUME SHORTLISTING - FULL PIPELINE BENCHMARK")
    print("=" * 65)

    # --------------------------------------------------------
    # Check resume directory
    # --------------------------------------------------------

    if not RESUME_DIR.exists():
        print(f"ERROR: Resume folder not found:\n{RESUME_DIR}")
        return

    resume_files = sorted(
        path
        for path in RESUME_DIR.iterdir()
        if path.is_file()
        and path.suffix.lower() in {".pdf", ".docx"}
    )

    if not resume_files:
        print("ERROR: No PDF or DOCX resumes found.")
        return

    print(f"Resume files found: {len(resume_files)}")
    print(f"Resume folder: {RESUME_DIR}")

    # --------------------------------------------------------
    # Stage 1: Resume extraction
    # --------------------------------------------------------

    print("\n[1/4] Extracting resumes...")

    candidates = []
    failed_files = []

    extraction_start = perf_counter()

    for index, file_path in enumerate(resume_files, start=1):
        try:
            candidate = analyze_resume(str(file_path))

            if not isinstance(candidate, dict):
                raise TypeError(
                    "analyze_resume did not return a dictionary."
                )

            candidate = dict(candidate)

            # Always preserve the source filename.
            candidate["filename"] = file_path.name

            # Fix: use the filename when the extracted name is blank.
            candidate["name"] = get_candidate_name(
                candidate,
                file_path.name,
            )

            # Ensure the text key exists for downstream services.
            candidate.setdefault("text", "")

            candidates.append(candidate)

            print(
                f"  {index}/{len(resume_files)} "
                f"OK - {file_path.name}"
            )

        except Exception as exc:
            failed_files.append({
                "filename": file_path.name,
                "error": str(exc),
            })

            print(
                f"  {index}/{len(resume_files)} "
                f"FAILED - {file_path.name}"
            )
            print(f"      Error: {exc}")

    extraction_seconds = perf_counter() - extraction_start

    if not candidates:
        print("\nERROR: No resumes could be extracted.")
        return

    # --------------------------------------------------------
    # Stage 2: Job description analysis
    # --------------------------------------------------------

    print("\n[2/4] Analysing job description...")

    jd_start = perf_counter()

    jd = analyze_job_description(JOB_DESCRIPTION)

    if not isinstance(jd, dict):
        raise TypeError(
            "analyze_job_description did not return a dictionary."
        )

    jd = dict(jd)

    detected_jd_skills = get_skills(jd)

    # Combine detected skills with configured benchmark priorities.
    combined_skills = list(dict.fromkeys(
        detected_jd_skills
        + PRIORITIES["must_have"]
        + PRIORITIES["important"]
        + PRIORITIES["preferred"]
    ))

    # Apply benchmark configuration.
    jd["skills"] = combined_skills
    jd["must_have_skills"] = PRIORITIES["must_have"]
    jd["important_skills"] = PRIORITIES["important"]
    jd["preferred_skills"] = PRIORITIES["preferred"]

    jd_seconds = perf_counter() - jd_start

    print(f"  JD skills detected: {len(detected_jd_skills)}")
    print(f"  JD skills configured: {len(combined_skills)}")

    # --------------------------------------------------------
    # Stage 3: Candidate ranking
    # --------------------------------------------------------

    print("\n[3/4] Ranking candidates...")

    ranking_start = perf_counter()

    ranked_candidates = rank_candidates(
        candidates,
        jd,
        use_semantic=USE_SEMANTIC,
        semantic_weight=SEMANTIC_WEIGHT,
    )

    ranking_seconds = perf_counter() - ranking_start

    if not isinstance(ranked_candidates, list):
        raise TypeError(
            "rank_candidates did not return a list."
        )

    # Make sure each candidate has a readable name in the report.
    for candidate in ranked_candidates:
        if not isinstance(candidate, dict):
            continue

        filename = candidate.get("filename", "")

        if not candidate.get("name"):
            candidate["name"] = get_candidate_name(
                candidate,
                filename or "unknown_resume",
            )

    print(f"  Candidates ranked: {len(ranked_candidates)}")

    # --------------------------------------------------------
    # Stage 4: Candidate shortlisting
    # --------------------------------------------------------

    print("\n[4/4] Applying shortlisting rules...")

    shortlist_start = perf_counter()

    priorities = configure_candidate_priorities(PRIORITIES)

    # Support implementations where configuration is in-place
    # and the function returns None or another non-dictionary.
    if not isinstance(priorities, dict):
        priorities = PRIORITIES

    final_candidates = shortlist_candidates(
        ranked_candidates,
        priorities,
        weights=CATEGORY_WEIGHTS,
        score_threshold=SCORE_THRESHOLD,
        min_must_have_coverage=MUST_HAVE_THRESHOLD,
        job_skills=combined_skills,
        use_semantic=USE_SEMANTIC,
        semantic_weight=SEMANTIC_WEIGHT,
    )

    shortlist_seconds = perf_counter() - shortlist_start

    if not isinstance(final_candidates, list):
        raise TypeError(
            "shortlist_candidates did not return a list."
        )

    # --------------------------------------------------------
    # Prepare the CSV report
    # --------------------------------------------------------

    report_rows = []

    for position, candidate in enumerate(
        final_candidates,
        start=1,
    ):
        if not isinstance(candidate, dict):
            continue

        filename = candidate.get("filename", "")

        # Ensure name never remains blank in the CSV.
        name = get_candidate_name(candidate, filename)

        score = get_score(candidate)

        shortlisted = candidate.get("shortlisted", False)

        matched_skills = candidate.get(
            "full_jd_matched_skills",
            candidate.get("matched_skills", []),
        )

        missing_skills = candidate.get(
            "full_jd_missing_skills",
            candidate.get("missing_skills", []),
        )

        reasons = candidate.get("shortlisting_reasons", [])

        report_rows.append({
            "rank": candidate.get("rank", position),
            "filename": filename,
            "name": name,
            "score": score,
            "shortlisted": shortlisted,
            "status": candidate.get(
                "shortlisting_status",
                "",
            ),
            "must_have_coverage": candidate.get(
                "must_have_coverage",
                "",
            ),
            "matched_skills": readable(matched_skills),
            "missing_skills": readable(missing_skills),
            "reasons": readable(reasons),
        })

    fieldnames = [
        "rank",
        "filename",
        "name",
        "score",
        "shortlisted",
        "status",
        "must_have_coverage",
        "matched_skills",
        "missing_skills",
        "reasons",
    ]

    # Write a UTF-8 CSV that opens correctly in common spreadsheet apps.
    with REPORT_PATH.open(
        "w",
        newline="",
        encoding="utf-8-sig",
    ) as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=fieldnames,
        )

        writer.writeheader()
        writer.writerows(report_rows)

    # --------------------------------------------------------
    # Calculate summary metrics
    # --------------------------------------------------------

    valid_scores = [
        row["score"]
        for row in report_rows
        if row["score"] is not None
    ]

    shortlisted_count = get_shortlisted_count(report_rows)

    total_measured_seconds = (
        extraction_seconds
        + jd_seconds
        + ranking_seconds
        + shortlist_seconds
    )

    # --------------------------------------------------------
    # Display results
    # --------------------------------------------------------

    print("\n" + "=" * 65)
    print("BENCHMARK RESULTS")
    print("=" * 65)

    print(f"Resume files found:       {len(resume_files)}")
    print(f"Successfully extracted:   {len(candidates)}")
    print(f"Failed extractions:       {len(failed_files)}")
    print(f"Candidates ranked:        {len(ranked_candidates)}")
    print(f"Candidates reported:      {len(report_rows)}")
    print(f"Shortlisted candidates:   {shortlisted_count}")
    print(f"Valid scores:             {len(valid_scores)}")

    if valid_scores:
        average_score = sum(valid_scores) / len(valid_scores)
        print(f"Average candidate score:  {average_score:.2f}%")
    else:
        print("Average candidate score:  unavailable")

    print("\nSTAGE TIMINGS")
    print("-" * 40)

    print(
        f"Resume extraction:        "
        f"{extraction_seconds:.3f} seconds"
    )
    print(
        f"JD analysis:              "
        f"{jd_seconds:.3f} seconds"
    )
    print(
        f"Candidate ranking:        "
        f"{ranking_seconds:.3f} seconds"
    )
    print(
        f"Shortlisting:              "
        f"{shortlist_seconds:.3f} seconds"
    )
    print(
        f"Total measured time:      "
        f"{total_measured_seconds:.3f} seconds"
    )

    if candidates:
        print(
            f"Average extraction time:  "
            f"{extraction_seconds / len(candidates):.3f} "
            f"seconds/resume"
        )

    # Check if any report names are blank.
    blank_names = sum(
        1
        for row in report_rows
        if not str(row.get("name", "")).strip()
    )

    print(f"\nBlank candidate names:    {blank_names}")
    print(f"CSV report:               {REPORT_PATH}")

    if failed_files:
        print("\nFILES THAT FAILED")
        print("-" * 40)

        for item in failed_files:
            print(f"- {item['filename']}: {item['error']}")

    print("\nTOP 5 CANDIDATES")
    print("-" * 65)

    for row in report_rows[:5]:
        print(
            f"Rank {row['rank']} | "
            f"{row['name']} | "
            f"Score: {row['score']} | "
            f"Shortlisted: {row['shortlisted']}"
        )

    print("\nIMPORTANT NOTES")
    print("-" * 40)
    print(
        "1. Synthetic profiles are test data, not real hiring data."
    )
    print(
        "2. Benchmark timing is specific to this computer and run."
    )
    print(
        "3. This test does not prove real-world matching accuracy."
    )
    print(
        "4. Zero shortlisted candidates can result from the configured "
        "eligibility rules; inspect the report before changing thresholds."
    )

    print("=" * 65)


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("\nBENCHMARK STOPPED WITH AN ERROR:")
        traceback.print_exc()