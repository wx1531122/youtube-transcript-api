from fastapi import FastAPI, HTTPException, Query, Path
from youtube_transcript_api import (
    YouTubeTranscriptApi,
    TranscriptsDisabled,
    VideoUnavailable,
    NoTranscriptFound,
    # NotTranslatable, # This is an alias for TranslationLanguageNotAvailable
    # TooManyRequests  # This is an alias for a standard requests exception, handled by their lib
)
from youtube_transcript_api._errors import (
    TranslationLanguageNotAvailable, # Specific error for translation
    TooManyRequests, # Added for handling rate limiting
    NotTranslatable, # Added for handling untranslatable transcripts
    NoTranscriptAvailable # Added for when no transcript at all can be found / list is empty
)
from youtube_transcript_api._transcripts import Transcript
from typing import List, Optional
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="YouTube Transcript API Wrapper",
    description="Provides an API interface to fetch YouTube video transcripts and translate them.",
    version="1.0.0",
)

# Import Pydantic models
from .schemas import (
    TranscriptMetadata,
    TranscriptListResponse,
    FetchedTranscriptSegment,
    FetchedTranscriptResponse,
    TranslatedTranscriptResponse,
    TranslationLanguageMetadata,
)

@app.get(
    "/",
    summary="Root Endpoint",
    description="A simple root endpoint to confirm the API is running."
)
async def read_root():
    return {"message": "Welcome to the YouTube Transcript API Wrapper"}

@app.get(
    "/videos/{video_id}/transcripts",
    response_model=TranscriptListResponse,
    summary="List Available Transcripts",
    description="Retrieves a list of all available manually created and auto-generated transcripts for a given YouTube video."
)
async def list_transcripts(
    video_id: str = Path(..., description="The ID of the YouTube video (e.g., 'dQw4w9WgXcQ').")
):
    try:
        api_transcript_list = YouTubeTranscriptApi().list_transcripts(video_id)

        manually_created = []
        for t_key in api_transcript_list._manually_created_transcripts:
            t = api_transcript_list._manually_created_transcripts[t_key]
            manually_created.append(
                TranscriptMetadata(
                    language=t.language,
                    language_code=t.language_code,
                    is_generated=t.is_generated,
                    is_translatable=t.is_translatable,
                    translation_languages=[
                        TranslationLanguageMetadata(language=lang.language, language_code=lang.language_code)
                        for lang in t.translation_languages
                    ]
                )
            )

        generated = []
        for t_key in api_transcript_list._generated_transcripts:
            t = api_transcript_list._generated_transcripts[t_key]
            generated.append(
                TranscriptMetadata(
                    language=t.language,
                    language_code=t.language_code,
                    is_generated=t.is_generated,
                    is_translatable=t.is_translatable,
                    translation_languages=[
                        TranslationLanguageMetadata(language=lang.language, language_code=lang.language_code)
                        for lang in t.translation_languages
                    ]
                )
            )

        return TranscriptListResponse(
            video_id=video_id,
            manually_created_transcripts=manually_created,
            generated_transcripts=generated,
        )
    except NoTranscriptAvailable as e:
        logger.error(f"No transcript available for video {video_id}: {e}")
        raise HTTPException(status_code=404, detail=f"No transcripts available for video {video_id}.")
    except TranscriptsDisabled as e:
        logger.warning(f"Transcripts disabled for video {video_id}: {e}")
        raise HTTPException(status_code=404, detail=f"Transcripts are disabled for video {video_id}.")
    except VideoUnavailable as e:
        logger.warning(f"Video {video_id} unavailable: {e}")
        raise HTTPException(status_code=404, detail=f"Video {video_id} not found or unavailable.")
    except TooManyRequests as e:
        logger.warning(f"Too many requests for video {video_id}: {e}")
        raise HTTPException(status_code=429, detail="Too many requests. Please try again later.")
    except Exception as e:
        logger.exception(f"An unexpected error occurred for video {video_id}: {e}")
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {str(e)}")

# Removed monkey-patched to_dict method and its definition


@app.get(
    "/videos/{video_id}/transcripts/fetch",
    response_model=FetchedTranscriptResponse,
    summary="Fetch a Specific Transcript",
    description="Fetches the content of a transcript for a given video in one of the specified languages. "
                "The `preserve_formatting` parameter is currently not implemented with `Transcript.fetch()`."
)
async def fetch_transcript(
    video_id: str = Path(..., description="The ID of the YouTube video (e.g., 'dQw4w9WgXcQ')."),
    language_codes: str = Query("en", description="Comma-separated list of language codes in order of preference (e.g., en,es,fr). The first found will be used."),
    preserve_formatting: Optional[bool] = Query(False, description="Whether to preserve HTML formatting elements (Note: this parameter is not fully effective with the current library method used for fetching by specific Transcript object).")
):
    try:
        langs = [lang.strip() for lang in language_codes.split(',')]

        api_transcript_list = YouTubeTranscriptApi().list_transcripts(video_id)

        found_transcript_obj: Optional[Transcript] = None
        # Iterate through preferred languages to find the first available transcript
        for lang_code in langs:
            # Attempt to find in manually created transcripts first
            if lang_code in api_transcript_list._manually_created_transcripts:
                found_transcript_obj = api_transcript_list._manually_created_transcripts[lang_code]
                break
            # Then attempt to find in generated transcripts
            if lang_code in api_transcript_list._generated_transcripts:
                found_transcript_obj = api_transcript_list._generated_transcripts[lang_code]
                break

        if not found_transcript_obj:
            # Pass the original video_id, list of attempted langs, and a clearer suffix
            raise NoTranscriptFound(video_id, langs, "Could not find transcript for any of the specified languages.")

        # Fetch the transcript content using the found Transcript object
        # Note: preserve_formatting is not a parameter for found_transcript_obj.fetch()
        # The library's get_transcript(video_id, languages=langs, preserve_formatting=preserve_formatting)
        # would handle it, but then we lose the direct Transcript object's metadata easily.
        # This implementation prioritizes getting metadata from the Transcript object.
        fetched_segments_raw = found_transcript_obj.fetch()

        return FetchedTranscriptResponse(
            video_id=video_id,
            language=found_transcript_obj.language,
            language_code=found_transcript_obj.language_code,
            is_generated=found_transcript_obj.is_generated,
            transcript=[FetchedTranscriptSegment.model_validate(segment) for segment in fetched_segments_raw]
        )
    except NoTranscriptFound as e:
        logger.info(f"No transcript found for video {video_id} with languages {language_codes}: {e}")
        raise HTTPException(status_code=404, detail=str(e))
    except TranscriptsDisabled as e:
        logger.warning(f"Transcripts disabled for video {video_id}: {e}")
        raise HTTPException(status_code=404, detail=f"Transcripts are disabled for video {video_id}.")
    except VideoUnavailable as e:
        logger.warning(f"Video {video_id} unavailable: {e}")
        raise HTTPException(status_code=404, detail=f"Video {video_id} not found or unavailable.")
    except TooManyRequests as e:
        logger.warning(f"Too many requests for video {video_id}: {e}")
        raise HTTPException(status_code=429, detail="Too many requests. Please try again later.")
    except Exception as e:
        logger.exception(f"An unexpected error occurred for video {video_id} with languages {language_codes}: {e}")
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {str(e)}")


@app.get(
    "/videos/{video_id}/transcripts/translate",
    response_model=TranslatedTranscriptResponse,
    summary="Translate a Transcript",
    description="Translates a transcript for a given video from a source language to a target language."
)
async def translate_transcript_endpoint(
    video_id: str = Path(..., description="The ID of the YouTube video (e.g., 'dQw4w9WgXcQ')."),
    source_language_code: str = Query(..., description="The language code of the original transcript (e.g., 'en')."),
    target_language_code: str = Query(..., description="The language code to translate the transcript to (e.g., 'es').")
):
    try:
        ytt_api = YouTubeTranscriptApi()
        api_transcript_list = ytt_api.list_transcripts(video_id)

        source_transcript_obj = api_transcript_list.find_transcript([source_language_code])
        # NoTranscriptFound is raised by find_transcript if not found.

        translated_transcript_api_obj = source_transcript_obj.translate(target_language_code)
        # TranslationLanguageNotAvailable or NotTranslatable can be raised here.

        fetched_translated_segments_raw = translated_transcript_api_obj.fetch()

        return TranslatedTranscriptResponse(
            video_id=video_id,
            source_language_code=source_language_code, # from input
            target_language_code=target_language_code, # from input
            language=translated_transcript_api_obj.language,
            language_code=translated_transcript_api_obj.language_code,
            is_generated=translated_transcript_api_obj.is_generated, # This indicates if the *translated* transcript is marked as generated; usually mirrors source
            transcript=[FetchedTranscriptSegment.model_validate(segment) for segment in fetched_translated_segments_raw]
        )
    except NoTranscriptFound as e:
        logger.info(f"No transcript found for source language {source_language_code} for video {video_id}: {e}")
        raise HTTPException(status_code=404, detail=f"No transcript found for source language '{source_language_code}' for video '{video_id}'.")
    except NotTranslatable as e:
        logger.warning(f"Transcript {source_language_code} for video {video_id} is not translatable to {target_language_code}: {e}")
        raise HTTPException(status_code=400, detail=f"Transcript for language '{source_language_code}' is not translatable to '{target_language_code}'. This might be because it's the same language or an invalid target.")
    except TranslationLanguageNotAvailable as e:
        logger.warning(f"Translation to {target_language_code} not available for {source_language_code} in video {video_id}: {e}")
        raise HTTPException(status_code=400, detail=f"Cannot translate from '{source_language_code}' to '{target_language_code}'. Target language is not available for this specific transcript.")
    except TranscriptsDisabled as e:
        logger.warning(f"Transcripts disabled for video {video_id}: {e}")
        raise HTTPException(status_code=404, detail=f"Transcripts are disabled for video {video_id}.")
    except VideoUnavailable as e:
        logger.warning(f"Video {video_id} unavailable: {e}")
        raise HTTPException(status_code=404, detail=f"Video {video_id} not found or unavailable.")
    except TooManyRequests as e:
        logger.warning(f"Too many requests for video {video_id}: {e}")
        raise HTTPException(status_code=429, detail="Too many requests. Please try again later.")
    except Exception as e:
        logger.exception(f"An unexpected error occurred during translation for video {video_id} from {source_language_code} to {target_language_code}: {e}")
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {str(e)}")
