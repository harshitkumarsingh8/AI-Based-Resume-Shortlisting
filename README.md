# AI-Based Resume Shortlisting System

An AI-assisted resume screening application built with **Python** and **Streamlit**. It accepts multiple PDF/DOCX resumes and a job description, extracts resume information, detects relevant skills, ranks candidates, explains matched and missing skills, and exports screening results as CSV files.

> **Project status:** A working prototype. The current workflow uses recruiter-selected Must-have, Important, and Preferred skill categories. Scores and shortlist decisions depend on the configured matching rules and should be validated for each role before real-world use.

## Key Features

- **Batch resume upload:** Process multiple PDF and DOCX resumes in one session.
- **Resume parsing:** Extract available resume text and fields such as skills, education, experience, projects, certifications, email, and phone.
- **Job description analysis:** Detect supported skills explicitly mentioned in the job description using a skill catalogue and aliases.
- **Priority-based matching:** Categorize role requirements as Must-have, Important, or Preferred.
- **Candidate ranking and shortlisting:** Calculate matching scores and apply the configured score and Must-have coverage thresholds.
- **Semantic matching:** Optionally incorporate semantic similarity through the project's matching services.
- **Explainability:** Display matched and missing skills, screening reasons, and text evidence snippets when available.
- **CSV exports:** Download a candidate ranking and a more detailed screening report.
- **Automated tests:** The current test suite has previously reported 122 passing tests in the development environment.

## Technology Stack

- Python 3.12
- Streamlit
- PyMuPDF (`pymupdf`) for PDF text extraction
- `python-docx` for DOCX processing
- pandas for tabular data and CSV exports
- scikit-learn for machine-learning utilities
- sentence-transformers for semantic embedding functionality
- Plotly for interactive visualizations where used
- pytest for automated tests

## Project Structure

```text
AI-Based-Resume-Shortlisting/
├── app.py
├── requirements.txt
├── app_backup.txt
├── services/
│   ├── resume_analyzer.py
│   ├── jd_analyzer.py
│   ├── matching_engine.py
│   ├── semantic_matcher.py
│   ├── candidate_ranker.py
│   └── shortlisting_engine.py
├── utils/
├── tests/
├── test_resume_parser.py
├── sample_resumes/
├── benchmark_resumes/
├── benchmark.py
├── benchmark_full_pipeline.py
├── generate_test_resumes.py
└── create_positive_test_resume.py
```

Some folders and files may change as the project develops. Benchmark reports and synthetic resumes are local test artifacts rather than production hiring data.

## Prerequisites

- Windows, macOS, or Linux
- Python 3.12 recommended
- pip
- Git, if you plan to publish the project to GitHub

## Installation (Windows PowerShell)

Open PowerShell in the project directory.

```powershell
# Create a virtual environment (skip if .venv already exists)
python -m venv .venv

# Activate it
.\.venv\Scripts\Activate.ps1

# Install dependencies
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

If PowerShell blocks activation, you can run the environment's Python directly instead:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Run the Application

From the project root with the virtual environment active:

```powershell
streamlit run app.py
```

Streamlit will print a local URL in the terminal. Open that URL in your browser.

## Basic Workflow

1. Paste the job description into the text area.
2. Upload one or more PDF/DOCX resumes.
3. Select **Analyse Resumes & Detect Skills**.
4. Review the skills detected from the job description.
5. Assign detected skills to **Must-have**, **Important**, and **Preferred** categories. The current app requires at least one Must-have skill.
6. Configure score thresholds, semantic matching, semantic weight, and category weights in the sidebar. Category weights must total exactly 100%.
7. Select **Run Shortlist Using My Priorities**.
8. Inspect candidate scores, matching coverage, missing skills, reasons, and evidence snippets.
9. Download the ranking CSV or the complete screening report CSV.

## Run Automated Tests

Run the tests from the project root:

```powershell
python -m pytest -q
```

A previous development run returned `122 passed`. Re-run the test command after changing code; results depend on the current files and environment.

## Resume Benchmark Utilities

The repository contains helper scripts used during development:

```powershell
# Resume extraction benchmark
python benchmark.py

# Full ranking/shortlisting benchmark
python benchmark_full_pipeline.py

# Generate synthetic DOCX resumes
python generate_test_resumes.py

# Generate one positive synthetic test resume
python create_positive_test_resume.py
```

These scripts are for development and load testing. Synthetic resumes are fictional, repeated template-based test data; benchmark throughput is machine-dependent and **does not establish real-world screening accuracy or fairness**. Do not present synthetic benchmark results as evidence that the system is accurate for real candidates.

## Configuration Notes

The app currently includes these default sidebar settings:

- Minimum overall score: **70%**
- Minimum Must-have coverage: **80%**
- Semantic matching: **enabled**
- Semantic weight: **30%**
- Category weights: Must-have **50%**, Important **30%**, Preferred **20%**

These are configurable example defaults, not universally valid hiring thresholds. Configure them for the actual job requirements and validate matching behavior before operational use.

## Limitations

- Skill detection relies on a supported catalogue, aliases, and extracted text. It can miss skills or misunderstand context.
- A detected mention is not proof of proficiency, experience duration, authenticity, or work quality.
- PDF extraction quality depends on the document; scanned/image-only PDFs may need OCR support if the current parser cannot extract their text.
- Semantic similarity is a matching signal, not a probability of job performance.
- The present workflow asks a recruiter to assign requirement priorities before scoring. It does not infer every role's mandatory criteria automatically.
- Benchmark test data is synthetic and limited; validate on representative, appropriately governed data before drawing performance conclusions.

## Responsible Use and Data Privacy

Use the tool as screening support and establish appropriate validation, access controls, retention practices, and a review process before processing real candidate information. Avoid using protected or sensitive personal attributes as ranking criteria. Provide a way to investigate errors and reconsider candidates affected by parsing or matching failures. Follow applicable employment, privacy, and AI rules for the jurisdiction where the system is used.

## Future Improvements

- More robust section-aware resume parsing and extraction confidence reporting
- Broader, tested skill alias coverage and requirements extraction
- Calibrated scoring with documented evaluation on representative data
- Larger performance tests, including 500 and 1,000 resumes
- More comprehensive error handling and UI regression tests
- Improved audit logs, recruiter configuration persistence, and deployment documentation

## License

No license is specified in the current project files. Add a license before publishing if you want to grant others explicit permission to use, modify, or distribute the project.
