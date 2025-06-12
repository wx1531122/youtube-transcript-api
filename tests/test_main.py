from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
import pytest

from web.main import app
from youtube_transcript_api import (
    VideoUnavailable,
    TranscriptsDisabled,
    NoTranscriptFound,
    TranslationLanguageNotAvailable,
    TooManyRequests,
    NotTranslatable,
    NoTranscriptAvailable
)
# Transcript, FetchedTranscript, TranscriptList are classes from the library, useful for spec
from youtube_transcript_api._transcripts import Transcript, TranscriptList
# FetchedTranscript is not directly used as a return type by the core library methods we mock,
# but individual transcript segment dicts are what Transcript.fetch() returns.

client = TestClient(app)

# --- Test for GET /videos/{video_id}/transcripts ---
# Corrected patch target to list_transcripts
@patch('youtube_transcript_api.YouTubeTranscriptApi.list_transcripts')
def test_list_transcripts_success(mock_api_list_transcripts):
    video_id = "test_video_id"

    mock_transcript_de = MagicMock(spec=Transcript)
    mock_transcript_de.video_id = video_id
    mock_transcript_de.language = "German"
    mock_transcript_de.language_code = "de"
    mock_transcript_de.is_generated = False
    mock_transcript_de.is_translatable = True
    mock_transcript_de.translation_languages = [
        MagicMock(language="English", language_code="en"),
        MagicMock(language="Spanish", language_code="es")
    ]

    mock_transcript_en_gen = MagicMock(spec=Transcript)
    mock_transcript_en_gen.video_id = video_id
    mock_transcript_en_gen.language = "English"
    mock_transcript_en_gen.language_code = "en"
    mock_transcript_en_gen.is_generated = True
    mock_transcript_en_gen.is_translatable = False
    mock_transcript_en_gen.translation_languages = []

    # Mock the TranscriptList object that YouTubeTranscriptApi().list_transcripts() returns
    mock_transcript_list_instance = MagicMock(spec=TranscriptList)
    mock_transcript_list_instance.video_id = video_id
    mock_transcript_list_instance._manually_created_transcripts = {'de': mock_transcript_de}
    mock_transcript_list_instance._generated_transcripts = {'en': mock_transcript_en_gen}

    # Configure the mock for the find_transcript method if needed by other tests, but not this one directly
    # mock_transcript_list_instance.find_transcript.return_value = ...

    mock_api_list_transcripts.return_value = mock_transcript_list_instance

    response = client.get(f"/videos/{video_id}/transcripts")

    assert response.status_code == 200
    data = response.json()
    assert data["video_id"] == video_id
    assert len(data["manually_created_transcripts"]) == 1
    assert data["manually_created_transcripts"][0]["language_code"] == "de"
    assert data["manually_created_transcripts"][0]["language"] == "German"
    assert data["manually_created_transcripts"][0]["is_translatable"] is True
    assert len(data["manually_created_transcripts"][0]["translation_languages"]) == 2
    assert data["manually_created_transcripts"][0]["translation_languages"][0]["language_code"] == "en"

    assert len(data["generated_transcripts"]) == 1
    assert data["generated_transcripts"][0]["language_code"] == "en"
    mock_api_list_transcripts.assert_called_once_with(video_id)

@patch('youtube_transcript_api.YouTubeTranscriptApi.list_transcripts')
def test_list_transcripts_video_unavailable(mock_api_list_transcripts):
    video_id = "unavailable_video"
    mock_api_list_transcripts.side_effect = VideoUnavailable(video_id)
    response = client.get(f"/videos/{video_id}/transcripts")
    assert response.status_code == 404
    assert "Video not found or unavailable" in response.json()["detail"]

@patch('youtube_transcript_api.YouTubeTranscriptApi.list_transcripts')
def test_list_transcripts_disabled(mock_api_list_transcripts):
    video_id = "disabled_video"
    mock_api_list_transcripts.side_effect = TranscriptsDisabled(video_id)
    response = client.get(f"/videos/{video_id}/transcripts")
    assert response.status_code == 404
    assert "Transcripts are disabled" in response.json()["detail"]

@patch('youtube_transcript_api.YouTubeTranscriptApi.list_transcripts')
def test_list_transcripts_no_transcript_available(mock_api_list_transcripts):
    video_id = "no_transcript_video_alt"
    mock_api_list_transcripts.side_effect = NoTranscriptAvailable(video_id)
    response = client.get(f"/videos/{video_id}/transcripts")
    assert response.status_code == 404
    assert "No transcripts available" in response.json()["detail"]

@patch('youtube_transcript_api.YouTubeTranscriptApi.list_transcripts')
def test_list_transcripts_too_many_requests(mock_api_list_transcripts):
    video_id = "rate_limit_video"
    mock_api_list_transcripts.side_effect = TooManyRequests()
    response = client.get(f"/videos/{video_id}/transcripts")
    assert response.status_code == 429
    assert "Too many requests" in response.json()["detail"]

# --- Test for GET /videos/{video_id}/transcripts/fetch ---
@patch('youtube_transcript_api.YouTubeTranscriptApi.list_transcripts')
def test_fetch_transcript_success(mock_api_list_transcripts):
    video_id = "fetch_video_id"
    lang_codes_query = "en,de"

    # Mock the Transcript object that will be "found"
    mock_en_transcript = MagicMock(spec=Transcript)
    mock_en_transcript.video_id = video_id
    mock_en_transcript.language = "English"
    mock_en_transcript.language_code = "en"
    mock_en_transcript.is_generated = False
    mock_en_transcript.fetch.return_value = [
        {"text": "Hello", "start": 0.0, "duration": 1.0},
        {"text": "world", "start": 1.0, "duration": 1.0},
    ]

    # Mock the TranscriptList object
    mock_transcript_list_instance = MagicMock(spec=TranscriptList)
    mock_transcript_list_instance.video_id = video_id
    # Simulate that the 'en' transcript is in manually_created_transcripts
    mock_transcript_list_instance._manually_created_transcripts = {'en': mock_en_transcript}
    mock_transcript_list_instance._generated_transcripts = {} # Empty for this case

    mock_api_list_transcripts.return_value = mock_transcript_list_instance

    response = client.get(f"/videos/{video_id}/transcripts/fetch?language_codes={lang_codes_query}&preserve_formatting=false")

    assert response.status_code == 200
    data = response.json()
    assert data["video_id"] == video_id
    assert data["language_code"] == "en" # Fetched 'en'
    assert data["language"] == "English"
    assert len(data["transcript"]) == 2
    assert data["transcript"][0]["text"] == "Hello"

    mock_api_list_transcripts.assert_called_once_with(video_id)
    mock_en_transcript.fetch.assert_called_once()


@patch('youtube_transcript_api.YouTubeTranscriptApi.list_transcripts')
def test_fetch_transcript_no_transcript_found(mock_api_list_transcripts):
    video_id = "no_transcript_video"
    lang_codes_query = "xx,yy"

    # Mock TranscriptList that doesn't contain 'xx' or 'yy'
    mock_transcript_list_instance = MagicMock(spec=TranscriptList)
    mock_transcript_list_instance.video_id = video_id
    mock_transcript_list_instance._manually_created_transcripts = {}
    mock_transcript_list_instance._generated_transcripts = {}
    # Side effect for find_transcript if it were used directly, but main.py iterates
    # For this test, an empty list means NoTranscriptFound will be raised by our logic
    mock_api_list_transcripts.return_value = mock_transcript_list_instance

    response = client.get(f"/videos/{video_id}/transcripts/fetch?language_codes={lang_codes_query}")
    assert response.status_code == 404
    # The detail message for NoTranscriptFound comes from its __str__ method.
    # We can check for a substring.
    assert "Could not find transcript for any of the specified languages" in response.json()["detail"]


# --- Test for GET /videos/{video_id}/transcripts/translate ---
@patch('youtube_transcript_api.YouTubeTranscriptApi.list_transcripts')
def test_translate_transcript_success(mock_api_list_transcripts):
    video_id = "translate_video_id"
    source_lang = "en"
    target_lang = "de"

    # Mock for the source transcript object
    mock_source_transcript = MagicMock(spec=Transcript)
    mock_source_transcript.video_id = video_id
    mock_source_transcript.language = "English"
    mock_source_transcript.language_code = source_lang
    # ... any other attributes your Pydantic model might access from source_transcript_obj

    # Mock for the translated transcript object (returned by source_transcript.translate())
    mock_translated_transcript_obj = MagicMock(spec=Transcript)
    mock_translated_transcript_obj.video_id = video_id # Usually same video_id
    mock_translated_transcript_obj.language = "German"    # Language of the translated content
    mock_translated_transcript_obj.language_code = target_lang # Language code of translated
    mock_translated_transcript_obj.is_generated = False # Example, could be True if source was generated

    # Mock the .fetch() call on the *translated* Transcript object
    mock_translated_transcript_obj.fetch.return_value = [
        {"text": "Hallo", "start": 0.0, "duration": 1.0},
        {"text": "Welt", "start": 1.0, "duration": 1.0},
    ]

    # Set up source_transcript.translate() to return the mock_translated_transcript_obj
    mock_source_transcript.translate.return_value = mock_translated_transcript_obj

    # Mock TranscriptList to contain the source_transcript via find_transcript
    # In main.py, we iterate over _manually_created_transcripts and _generated_transcripts
    # So, we need to place mock_source_transcript there.
    mock_transcript_list_instance = MagicMock(spec=TranscriptList)
    mock_transcript_list_instance.video_id = video_id
    mock_transcript_list_instance._manually_created_transcripts = {source_lang: mock_source_transcript}
    mock_transcript_list_instance._generated_transcripts = {}

    # If find_transcript was used, it would be:
    # mock_transcript_list_instance.find_transcript.return_value = mock_source_transcript

    mock_api_list_transcripts.return_value = mock_transcript_list_instance

    response = client.get(f"/videos/{video_id}/transcripts/translate?source_language_code={source_lang}&target_language_code={target_lang}")

    assert response.status_code == 200
    data = response.json()
    assert data["video_id"] == video_id
    assert data["source_language_code"] == source_lang
    assert data["target_language_code"] == target_lang
    assert data["language_code"] == target_lang
    assert data["language"] == "German"
    assert len(data["transcript"]) == 2
    assert data["transcript"][0]["text"] == "Hallo"

    mock_api_list_transcripts.assert_called_once_with(video_id)
    # find_transcript is not directly called on the list in main.py's translate logic, it's iterated.
    # So, no assertion for find_transcript directly on the list mock.
    mock_source_transcript.translate.assert_called_once_with(target_lang)
    mock_translated_transcript_obj.fetch.assert_called_once()


@patch('youtube_transcript_api.YouTubeTranscriptApi.list_transcripts')
def test_translate_transcript_source_not_found(mock_api_list_transcripts):
    video_id = "translate_video_source_not_found"

    # Simulate TranscriptList that doesn't contain the source language 'en'
    mock_transcript_list_instance = MagicMock(spec=TranscriptList)
    mock_transcript_list_instance.video_id = video_id
    mock_transcript_list_instance._manually_created_transcripts = {} # 'en' not here
    mock_transcript_list_instance._generated_transcripts = {}   # 'en' not here
    # If find_transcript were used:
    # mock_transcript_list_instance.find_transcript.side_effect = NoTranscriptFound(video_id, ['en'], '_manually_created_transcripts', {'en'})

    mock_api_list_transcripts.return_value = mock_transcript_list_instance

    response = client.get(f"/videos/{video_id}/transcripts/translate?source_language_code=en&target_language_code=de")
    assert response.status_code == 404
    assert "No transcript found for source language 'en'" in response.json()["detail"]

@patch('youtube_transcript_api.YouTubeTranscriptApi.list_transcripts')
def test_translate_transcript_translation_not_available(mock_api_list_transcripts):
    video_id = "translate_video_target_not_available"

    mock_source_transcript = MagicMock(spec=Transcript)
    # The video_id parameter for TranslationLanguageNotAvailable is the first one.
    mock_source_transcript.translate.side_effect = TranslationLanguageNotAvailable(video_id)

    mock_transcript_list_instance = MagicMock(spec=TranscriptList)
    mock_transcript_list_instance._manually_created_transcripts = {'en': mock_source_transcript}
    mock_transcript_list_instance._generated_transcripts = {}
    # If find_transcript were used:
    # mock_transcript_list_instance.find_transcript.return_value = mock_source_transcript

    mock_api_list_transcripts.return_value = mock_transcript_list_instance

    response = client.get(f"/videos/{video_id}/transcripts/translate?source_language_code=en&target_language_code=xx")
    assert response.status_code == 400 # As defined in main.py for this error
    assert "Cannot translate from 'en' to 'xx'" in response.json()["detail"]

@patch('youtube_transcript_api.YouTubeTranscriptApi.list_transcripts')
def test_translate_transcript_not_translatable(mock_api_list_transcripts):
    video_id = "translate_video_not_translatable"

    mock_source_transcript = MagicMock(spec=Transcript)
    mock_source_transcript.translate.side_effect = NotTranslatable(video_id)

    mock_transcript_list_instance = MagicMock(spec=TranscriptList)
    mock_transcript_list_instance._manually_created_transcripts = {'en': mock_source_transcript}
    mock_transcript_list_instance._generated_transcripts = {}
    mock_api_list_transcripts.return_value = mock_transcript_list_instance

    response = client.get(f"/videos/{video_id}/transcripts/translate?source_language_code=en&target_language_code=de")
    assert response.status_code == 400
    assert "is not translatable to 'de'" in response.json()["detail"]

# Example for TooManyRequests on fetch_transcript
@patch('youtube_transcript_api.YouTubeTranscriptApi.list_transcripts')
def test_fetch_transcript_too_many_requests(mock_api_list_transcripts):
    video_id = "fetch_rate_limit_video"
    mock_api_list_transcripts.side_effect = TooManyRequests()
    response = client.get(f"/videos/{video_id}/transcripts/fetch?language_codes=en")
    assert response.status_code == 429 # list_transcripts is called first
    assert "Too many requests" in response.json()["detail"]

# Example for TooManyRequests on translate_transcript
@patch('youtube_transcript_api.YouTubeTranscriptApi.list_transcripts')
def test_translate_transcript_too_many_requests(mock_api_list_transcripts):
    video_id = "translate_rate_limit_video"
    mock_api_list_transcripts.side_effect = TooManyRequests()
    response = client.get(f"/videos/{video_id}/transcripts/translate?source_language_code=en&target_language_code=de")
    assert response.status_code == 429 # list_transcripts is called first
    assert "Too many requests" in response.json()["detail"]

# TODO: Add tests for other specific error conditions from youtube-transcript-api if they can be distinctly triggered.
# e.g. CookiePathInvalid, CookiesInvalid, FailedToCreateConsentCookie - these might be harder to simulate
# if they occur deep within the library's HTTP handling rather than at the API method call level.
# The current set covers API interaction logic well.
# Test for the root endpoint
def test_read_root():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "Welcome to the YouTube Transcript API Wrapper"}

# Test for VideoUnavailable in fetch_transcript
@patch('youtube_transcript_api.YouTubeTranscriptApi.list_transcripts')
def test_fetch_transcript_video_unavailable(mock_api_list_transcripts):
    video_id = "fetch_unavailable_video"
    mock_api_list_transcripts.side_effect = VideoUnavailable(video_id)
    response = client.get(f"/videos/{video_id}/transcripts/fetch?language_codes=en")
    assert response.status_code == 404
    assert "Video not found or unavailable" in response.json()["detail"]

# Test for TranscriptsDisabled in fetch_transcript
@patch('youtube_transcript_api.YouTubeTranscriptApi.list_transcripts')
def test_fetch_transcript_transcripts_disabled(mock_api_list_transcripts):
    video_id = "fetch_disabled_video"
    mock_api_list_transcripts.side_effect = TranscriptsDisabled(video_id)
    response = client.get(f"/videos/{video_id}/transcripts/fetch?language_codes=en")
    assert response.status_code == 404
    assert "Transcripts are disabled" in response.json()["detail"]

# Test for VideoUnavailable in translate_transcript
@patch('youtube_transcript_api.YouTubeTranscriptApi.list_transcripts')
def test_translate_transcript_video_unavailable(mock_api_list_transcripts):
    video_id = "translate_unavailable_video"
    mock_api_list_transcripts.side_effect = VideoUnavailable(video_id)
    response = client.get(f"/videos/{video_id}/transcripts/translate?source_language_code=en&target_language_code=de")
    assert response.status_code == 404
    assert "Video not found or unavailable" in response.json()["detail"]

# Test for TranscriptsDisabled in translate_transcript
@patch('youtube_transcript_api.YouTubeTranscriptApi.list_transcripts')
def test_translate_transcript_transcripts_disabled(mock_api_list_transcripts):
    video_id = "translate_disabled_video"
    mock_api_list_transcripts.side_effect = TranscriptsDisabled(video_id)
    response = client.get(f"/videos/{video_id}/transcripts/translate?source_language_code=en&target_language_code=de")
    assert response.status_code == 404
    assert "Transcripts are disabled" in response.json()["detail"]

# Test for NoTranscriptAvailable in fetch_transcript (if list_transcripts raises it first)
@patch('youtube_transcript_api.YouTubeTranscriptApi.list_transcripts')
def test_fetch_no_transcript_available(mock_list_transcripts):
    video_id = "fetch_no_transcript_video"
    mock_list_transcripts.side_effect = NoTranscriptAvailable(video_id)
    response = client.get(f"/videos/{video_id}/transcripts/fetch?language_codes=en")
    assert response.status_code == 404 # Caught by list_transcripts call
    assert "No transcripts available" in response.json()["detail"]

# Test for NoTranscriptAvailable in translate_transcript (if list_transcripts raises it first)
@patch('youtube_transcript_api.YouTubeTranscriptApi.list_transcripts')
def test_translate_no_transcript_available(mock_list_transcripts):
    video_id = "translate_no_transcript_video"
    mock_list_transcripts.side_effect = NoTranscriptAvailable(video_id)
    response = client.get(f"/videos/{video_id}/transcripts/translate?source_language_code=en&target_language_code=de")
    assert response.status_code == 404 # Caught by list_transcripts call
    assert "No transcripts available" in response.json()["detail"]

# Test case where list_transcripts is successful but the specific language for fetch is not found
@patch('youtube_transcript_api.YouTubeTranscriptApi.list_transcripts')
def test_fetch_transcript_specific_lang_not_in_list(mock_api_list_transcripts):
    video_id = "fetch_specific_lang_missing"
    lang_codes_query = "xx" # Language not in the mock list

    mock_transcript_de = MagicMock(spec=Transcript)
    mock_transcript_de.language_code = "de"
    # ... other attrs

    mock_transcript_list_instance = MagicMock(spec=TranscriptList)
    mock_transcript_list_instance.video_id = video_id
    mock_transcript_list_instance._manually_created_transcripts = {'de': mock_transcript_de}
    mock_transcript_list_instance._generated_transcripts = {}
    mock_api_list_transcripts.return_value = mock_transcript_list_instance

    response = client.get(f"/videos/{video_id}/transcripts/fetch?language_codes={lang_codes_query}")

    assert response.status_code == 404
    assert "Could not find transcript for any of the specified languages" in response.json()["detail"]

# Test case where list_transcripts is successful but the specific source language for translate is not found
@patch('youtube_transcript_api.YouTubeTranscriptApi.list_transcripts')
def test_translate_transcript_specific_source_lang_not_in_list(mock_api_list_transcripts):
    video_id = "translate_specific_source_lang_missing"
    source_lang_query = "xx" # Language not in the mock list
    target_lang_query = "de"

    mock_transcript_de = MagicMock(spec=Transcript)
    mock_transcript_de.language_code = "de"
    # ... other attrs

    mock_transcript_list_instance = MagicMock(spec=TranscriptList)
    mock_transcript_list_instance.video_id = video_id
    mock_transcript_list_instance._manually_created_transcripts = {'de': mock_transcript_de} # Contains 'de' but not 'xx'
    mock_transcript_list_instance._generated_transcripts = {}
    mock_api_list_transcripts.return_value = mock_transcript_list_instance

    response = client.get(f"/videos/{video_id}/transcripts/translate?source_language_code={source_lang_query}&target_language_code={target_lang_query}")

    assert response.status_code == 404
    assert f"No transcript found for source language '{source_lang_query}'" in response.json()["detail"]
