from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import pandas as pd

from services.resume_analyzer import analyze_resume


# ============================================================
# CONFIGURATION
# ============================================================

PROJECT_DIR = Path(__file__).resolve().parent
RESUME_DIR = PROJECT_DIR / "benchmark_resumes"
REPORT_PATH = PROJECT_DIR / "benchmark_report.csv"

SUPPORTED_EXTENSIONS = {".pdf", ".docx"}

TEXT_KEYS = (
    "text",
    "full_text",
    "extracted_text",
    "raw_text",
    "content",
    "resume_text",
    "resume_content",
)


# ============================================================
# HELPERS
# ============================================================

def get_resume_text(data: dict[str, Any]) -> str:
    """Return extracted resume text, if available."""
    for key in TEXT_KEYS:
        value = data.get(key)

        if isinstance(value, str) and value.strip():
            return value.strip()

    return ""


def count_skills(data: dict[str, Any]) -> int:
    """Count distinct skills returned by the resume analyser."""
    skills = data.get("skills", [])

    if isinstance(skills, dict):
        values = list(skills.keys())
    elif isinstance(skills, (list, tuple, set)):
        values = list(skills)
    elif isinstance(skills, str) and skills.strip():
        values = [skills]
    else:
        values = []

    normalized = {
        str(skill).strip().casefold()
        for skill in values
        if str(skill).strip()
    }

    return len(normalized)


# ============================================================
# BENCHMARK
# ============================================================

def main() -> None:
    print("=" * 60)
    print("AI RESUME SCREENING - EXTRACTION BENCHMARK")
    print("=" * 60)

    if not RESUME_DIR.exists():
        print(f"ERROR: Resume folder not found:\n{RESUME_DIR}")
        return

    resume_files = sorted(
        (
            path
            for path in RESUME_DIR.iterdir()
            if path.is_file()
            and path.suffix.casefold() in SUPPORTED_EXTENSIONS
        ),
        key=lambda path: path.name.casefold(),
    )

    if not resume_files:
        print("No PDF or DOCX files found in benchmark_resumes.")
        return

    print(f"Resume folder: {RESUME_DIR}")
    print(f"Files found: {len(resume_files)}")
    print("-" * 60)

    results: list[dict[str, Any]] = []
    total_start = time.perf_counter()

    for index, resume_path in enumerate(resume_files, start=1):
        print(
            f"[{index}/{len(resume_files)}] "
            f"Analysing: {resume_path.name}"
        )

        start = time.perf_counter()

        try:
            data = analyze_resume(str(resume_path))
            elapsed = time.perf_counter() - start

            if not isinstance(data, dict):
                raise TypeError(
                    "analyze_resume() did not return a dictionary."
                )

            text = get_resume_text(data)

            results.append({
                "filename": resume_path.name,
                "status": "Success",
                "processing_seconds": round(elapsed, 4),
                "extracted_text_characters": len(text),
                "detected_skill_count": count_skills(data),
                "error": "",
            })

            print(
                f"    SUCCESS | {elapsed:.2f}s | "
                f"{len(text)} text characters | "
                f"{count_skills(data)} detected skills"
            )

        except Exception as exc:
            elapsed = time.perf_counter() - start

            results.append({
                "filename": resume_path.name,
                "status": "Failed",
                "processing_seconds": round(elapsed, 4),
                "extracted_text_characters": 0,
                "detected_skill_count": 0,
                "error": f"{type(exc).__name__}: {exc}",
            })

            print(f"    FAILED  | {elapsed:.2f}s | {exc}")

    total_seconds = time.perf_counter() - total_start

    report = pd.DataFrame(results)
    report.to_csv(REPORT_PATH, index=False, encoding="utf-8-sig")

    successful = int((report["status"] == "Success").sum())
    failed = int((report["status"] == "Failed").sum())

    successful_times = report.loc[
        report["status"] == "Success",
        "processing_seconds",
    ]

    print("\n" + "=" * 60)
    print("BENCHMARK SUMMARY")
    print("=" * 60)
    print(f"Total files:          {len(resume_files)}")
    print(f"Successfully parsed:  {successful}")
    print(f"Failed:               {failed}")
    print(f"Total elapsed time:   {total_seconds:.2f} seconds")

    if successful_times.empty:
        print("Average per resume:   N/A")
    else:
        print(
            f"Average per resume:   "
            f"{successful_times.mean():.2f} seconds"
        )
        print(
            f"Slowest successful:   "
            f"{successful_times.max():.2f} seconds"
        )

    print(f"\nReport saved to:\n{REPORT_PATH}")
    print(
        "\nNOTE: This measures resume extraction only. "
        "It does not measure full ranking or semantic matching."
    )


if __name__ == "__main__":
    main()