import os
import time
import json
import logging
import typing_extensions as typing
import google.generativeai as genai
from google.ai.generativelanguage_v1beta.types import content

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Define the expected JSON structure for Type Safety
class VideoSegment(typing.TypedDict):
    start_time: str
    end_time: str
    virality_score: int
    reasoning: str
    suggested_title: str

class AIProcessor:
    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("API Key is required for AIProcessor")
        
        genai.configure(api_key=api_key)
        
        self.model_name = "gemini-2.5-flash"
        
        # We configure the model to output strict JSON
        self.generation_config = genai.GenerationConfig(
            response_mime_type="application/json",
            response_schema=VideoSegment
        )

    def upload_file(self, file_path: str):
        """Uploads file to Gemini and waits for processing to complete."""
        logger.info(f"Uploading file to Gemini: {file_path}")
        
        try:
            video_file = genai.upload_file(path=file_path)
            
            # Wait for processing (Gemini needs time to 'watch' the video)
            while video_file.state.name == "PROCESSING":
                logger.info("Waiting for video to process...")
                time.sleep(2)
                video_file = genai.get_file(video_file.name)

            if video_file.state.name == "FAILED":
                raise ValueError("Video processing failed on Google servers.")

            logger.info(f"Video ready: {video_file.name}")
            return video_file

        except Exception as e:
            logger.error(f"Upload failed: {str(e)}")
            raise

    def get_timestamps(self, file_path: str) -> dict:
        """
        Orchestrates the analysis: Upload -> Analyze -> Return JSON
        """
        video_file = None
        try:
            # 1. Upload
            video_file = self.upload_file(file_path)

            # 2. Initialize Model
            model = genai.GenerativeModel(
                model_name=self.model_name,
                generation_config=self.generation_config
            )

            # 3. The Prompt
            prompt = (
                "You are an expert video editor for viral YouTube Shorts. "
                "Analyze this video and identify the single most engaging, contiguous segment "
                "that is BETWEEN 60 - 90 SECONDS long. "
                "The segment must stand alone and make sense without context. "
                "Prioritize high energy, emotional moments, or clear punchlines. "
                "Return the start and end timestamps in strictly 'HH:MM:SS' format."
            )

            logger.info("Sending prompt to Gemini...")
            response = model.generate_content([video_file, prompt])

            # 4. Parse Response
            # Since we forced JSON mode, response.text should be valid JSON
            result = json.loads(response.text)
            logger.info(f"AI Analysis Complete: {result}")
            
            return {
                "status": "success",
                "data": result
            }

        except Exception as e:
            logger.error(f"AI Analysis failed: {str(e)}")
            return {
                "status": "error",
                "message": str(e)
            }
        
        finally:
            # 5. Cleanup
            if video_file:
                logger.info("Cleaning up file from Google Cloud...")
                genai.delete_file(video_file.name)