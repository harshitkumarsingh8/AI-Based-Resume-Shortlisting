import pymupdf
from docx import Document
from pathlib import Path


def extract_text_from_pdf(file_path):
    """Extract text from a PDF resume."""
    text = []

    with pymupdf.open(file_path) as pdf:
        for page in pdf:
            text.append(page.get_text())

    return "\n".join(text).strip()


def extract_text_from_docx(file_path):
    """Extract text from a DOCX resume."""
    document = Document(file_path)

    paragraphs = [
        paragraph.text
        for paragraph in document.paragraphs
        if paragraph.text.strip()
    ]

    return "\n".join(paragraphs).strip()


def extract_resume_text(file_path):
    """Extract text based on the resume file extension."""
    path = Path(file_path)
    extension = path.suffix.lower()

    if extension == ".pdf":
        return extract_text_from_pdf(path)

    if extension == ".docx":
        return extract_text_from_docx(path)

    raise ValueError("Unsupported file type. Use PDF or DOCX.")