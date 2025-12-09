import os
import logging
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Import our "Worker" services
from services.downloader import VideoDownloader
from services.intelligence import AIProcessor
from services.editor import VideoEditor
from services.uploader import DriveUploader

# Configure Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Director")

# Initialize the App
app = FastAPI(title="Shorts Worker V1")

# --- Configuration ---
# Load API Key for Gemini
GEMINI_API_KEY = os.getenv("GOOGLE_API_KEY")
if not GEMINI_API_KEY:
    logger.warning("GOOGLE_API_KEY not found in environment variables!")

# --- Data Models ---
class VideoRequest(BaseModel):
    youtube_url: str

# --- Helper: Cleanup Function ---
def cleanup_files(file_paths: list):
    """Deletes temporary files to save disk space on Railway."""
    for path in file_paths:
        if path and os.path.exists(path):
            try:
                os.remove(path)
                logger.info(f"Cleaned up file: {path}")
            except Exception as e:
                logger.error(f"Failed to delete {path}: {e}")

# --- The Main Endpoint ---
@app.post("/process-video")
async def process_video(request: VideoRequest, background_tasks: BackgroundTasks):
    """
    Orchestrates the full pipeline: Download -> AI Analyze -> Edit -> Upload.
    """
    logger.info(f"Received request for: {request.youtube_url}")
    
    # Initialize Services
    # We initialize here to ensure fresh state for every request
    try:
        downloader = VideoDownloader()
        ai_processor = AIProcessor(api_key=GEMINI_API_KEY)
        editor = VideoEditor()
        uploader = DriveUploader()
    except Exception as e:
        logger.error(f"Service Initialization Failed: {e}")
        raise HTTPException(status_code=500, detail=f"Service Start Failed: {str(e)}")

    # Track files for cleanup
    downloaded_file = None
    processed_file = None

    try:
        # 1. DOWNLOADER
        logger.info(">>> Step 1: Downloading...")
        dl_result = downloader.download_video(request.youtube_url)
        if dl_result.get("status") == "error":
            raise Exception(f"Download failed: {dl_result.get('message')}")
        
        downloaded_file = dl_result["file_path"]
        video_title = dl_result.get("title", "Untitled Video")
        logger.info(f"Download complete: {downloaded_file}")

        # 2. INTELLIGENCE (Gemini 2.5 Flash)
        logger.info(">>> Step 2: AI Analysis...")
        ai_result = ai_processor.get_timestamps(downloaded_file)
        if ai_result.get("status") == "error":
            raise Exception(f"AI Analysis failed: {ai_result.get('message')}")
        
        # Extract data from AI response
        ai_data = ai_result["data"]
        start_time = ai_data["start_time"]
        end_time = ai_data["end_time"]
        viral_title = ai_data.get("suggested_title", video_title)
        logger.info(f"AI Selected: {start_time} to {end_time} | Title: {viral_title}")

        # 3. EDITOR (FFmpeg)
        logger.info(">>> Step 3: Editing...")
        edit_result = editor.process_video(downloaded_file, start_time, end_time)
        if edit_result.get("status") == "error":
            raise Exception(f"Editing failed: {edit_result.get('message')}")
        
        processed_file = edit_result["file_path"]
        logger.info(f"Editing complete: {processed_file}")

        # 4. UPLOADER (Google Drive)
        logger.info(">>> Step 4: Uploading...")
        upload_result = uploader.upload_file(processed_file, viral_title)
        if upload_result.get("status") == "error":
            raise Exception(f"Upload failed: {upload_result.get('message')}")

        drive_link = upload_result["drive_link"]
        logger.info(f"Pipeline Success! Link: {drive_link}")

        # Success Response
        return {
            "status": "success",
            "original_video": video_title,
            "generated_short_title": viral_title,
            "drive_link": drive_link,
            "timestamps": {
                "start": start_time,
                "end": end_time
            },
            "reasoning": ai_data.get("reasoning", "")
        }

    except Exception as e:
        logger.error(f"Pipeline Failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        # Cleanup runs regardless of success or failure
        # We use BackgroundTasks so the user gets the response instantly,
        # while the server deletes files in the background.
        background_tasks.add_task(cleanup_files, [downloaded_file, processed_file])

@app.get("/")
def health_check():
    return {"status": "online", "service": "Shorts Worker V1"}