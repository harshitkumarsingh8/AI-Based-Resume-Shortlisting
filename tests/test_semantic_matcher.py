
import numpy as np
import pytest

from services.semantic_matcher import compare_texts


class FakeEmbeddingModel:
    def encode(
        self,
        texts,
        normalize_embeddings=True,
        convert_to_numpy=True,
    ):
        return np.array([
            [1.0, 0.0],
            [0.8, 0.6],
        ])


def test_semantic_similarity_uses_embeddings():
    result = compare_texts(
        "Python data analysis project",
        "Python analytics role",
        model=FakeEmbeddingModel(),
    )

    assert result["semantic_similarity"] == pytest.approx(0.8)
    assert result["semantic_score"] == 80.0
    assert "limitation" in result


def test_empty_resume_text_raises_error():
    with pytest.raises(ValueError, match="Resume text cannot be empty"):
        compare_texts("", "Python developer")


def test_empty_job_description_raises_error():
    with pytest.raises(
        ValueError,
        match="Job description cannot be empty",
    ):
        compare_texts("Python developer resume", "")


def test_non_string_resume_raises_error():
    with pytest.raises(TypeError, match="Resume text must be a string"):
        compare_texts(None, "Python developer")


def test_non_string_job_description_raises_error():
    with pytest.raises(
        TypeError,
        match="Job description must be a string",
    ):
        compare_texts("Python developer resume", None)
