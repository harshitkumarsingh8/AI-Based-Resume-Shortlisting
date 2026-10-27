
from functools import lru_cache

import numpy as np


MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"


@lru_cache(maxsize=1)
def _load_model():
    """Load the embedding model once and reuse it."""
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(MODEL_NAME)


def compare_texts(
    resume_text: str,
    job_description: str,
    model=None,
) -> dict:
    """
    Compare resume and job-description meaning using text embeddings.

    The returned score is a similarity indicator, not a probability
    of hiring success or a verified measure of candidate ability.
    """
    if not isinstance(resume_text, str):
        raise TypeError("Resume text must be a string.")

    if not isinstance(job_description, str):
        raise TypeError("Job description must be a string.")

    resume_text = resume_text.strip()
    job_description = job_description.strip()

    if not resume_text:
        raise ValueError("Resume text cannot be empty.")

    if not job_description:
        raise ValueError("Job description cannot be empty.")

    embedding_model = model if model is not None else _load_model()

    embeddings = embedding_model.encode(
        [resume_text, job_description],
        normalize_embeddings=True,
        convert_to_numpy=True,
    )

    embeddings = np.asarray(embeddings, dtype=float)

    if embeddings.shape[0] != 2 or embeddings.ndim != 2:
        raise ValueError("The embedding model returned an invalid shape.")

    if not np.isfinite(embeddings).all():
        raise ValueError("The embedding model returned invalid values.")

    resume_vector, job_vector = embeddings

    # Embeddings are normalized, so their dot product is cosine similarity.
    cosine_similarity = float(np.dot(resume_vector, job_vector))
    cosine_similarity = float(np.clip(cosine_similarity, -1.0, 1.0))

    return {
        "semantic_similarity": round(cosine_similarity, 4),
        "semantic_score": round(max(0.0, cosine_similarity) * 100, 2),
        "model": MODEL_NAME,
        "method": "Sentence-transformer embeddings with cosine similarity",
        "limitation": (
            "Semantic similarity is not a probability of hiring success. "
            "It does not independently verify skills, experience, "
            "qualifications, or eligibility."
        ),
    }
