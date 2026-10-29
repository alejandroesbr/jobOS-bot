from unittest.mock import MagicMock

import pytest

from src.adapters.ai.gemini_client import GeminiClient


def test_gemini_client_offline_fallback() -> None:
    # Without API key, operates in graceful offline mode
    client = GeminiClient(api_key="")
    assert client.is_available is False

    qa_fallback = client.generate_qa_fallback("¿Años con React?", "number", "profile context")
    assert qa_fallback != ""

    tailor_md = client.tailor_cv("Junior Dev", "React & Node", "My CV")
    assert "ATS Gap" in tailor_md

    prep_md = client.prepare_interview("Junior Dev", "TechCorp", "React & Node", ["React", "Node.js"])
    assert "Guía de Preparación Técnica" in prep_md


def test_gemini_client_with_mocked_genai() -> None:
    client = GeminiClient(api_key="test-mock-key")
    mock_genai_client = MagicMock()
    mock_response = MagicMock()
    mock_response.text = "Mocked AI Response"
    mock_genai_client.models.generate_content.return_value = mock_response
    client._client = mock_genai_client

    result = client.generate_qa_fallback("¿Años con React?", "number", "context")
    assert result == "Mocked AI Response"
    assert mock_genai_client.models.generate_content.called
