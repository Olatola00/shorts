from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import google.generativeai as genai
import yt_dlp
import ffmpeg
import os
import time
import uuid
import json

app = FastAPI()

# --- CONFIGURATION ---
# Load these from Railway Variables
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
DRIVE_FOLDER_ID = os.environ.get("DRIVE_FOLDER_ID") 
# On Railway, paste the content of service_account.json into a variable named SERVICE_ACCOUNT_JSON
SERVICE_ACCOUNT_INFO = json.loads(os.environ.get("SERVICE_ACCOUNT_JSON"))

# Configure Gemini
genai.configure(api_key=GEMINI_API_KEY)

class VideoRequest(BaseModel):
    url: str
    prompt: str = "Find the most viral 30-60s segment. Focus on high energy moments."

def upload_to_drive(file_path, filename):
    """Uploads file to Google Drive and makes it public/shareable"""
    creds = service_account.Credentials.from_service_account_info(
        SERVICE_ACCOUNT_INFO, scopes=['https://www.googleapis.com/auth/drive']
    )
    service = build('drive', 'v3', credentials=creds)

    file_metadata = {
        'name': filename,
        'parents': [DRIVE_FOLDER_ID]
    }
    media = MediaFileUpload(file_path, mimetype='video/mp4', resumable=True)
    
    # 1. Upload
    file = service.files().create(
        body=file_metadata, media_body=media, fields='id, webViewLink'
    ).execute()
    file_id = file.get('id')

    # 2. Make Public (Reader)
    service.permissions().create(
        fileId=file_id,
        body={'role': 'reader', 'type': 'anyone'}
    ).execute()

    return file.get('webViewLink')

@app.post("/process-video")
async def process_video(request: VideoRequest):
    job_id = str(uuid.uuid4())[:8]
    raw_path = f"/tmp/{job_id}_raw.mp4"
    final_path = f"/tmp/{job_id}_short.mp4"

    try:
        # 1. Download Video
        print(f"⬇️ Downloading: {request.url}")
        ydl_opts = {'format': 'best[ext=mp4]', 'outtmpl': raw_path, 'quiet': True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([request.url])

        # 2. Upload to Gemini for Analysis
        print("🧠 Analyzing with Gemini...")
        video_file = genai.upload_file(path=raw_path)
        
        while video_file.state.name == "PROCESSING":
            time.sleep(2)
            video_file = genai.get_file(video_file.name)

        # 3. Ask Gemini for Timestamps
        model = genai.GenerativeModel("gemini-1.5-flash")
        prompt = f"""
        Analyze this video based on this request: "{request.prompt}"
        Return JSON ONLY with these keys:
        - start (string in HH:MM:SS format)
        - duration (integer in seconds)
        - crop_focus (string: 'center', 'left', or 'right')
        """
        result = model.generate_content([video_file, prompt], generation_config={"response_mime_type": "application/json"})
        data = json.loads(result.text)
        
        print(f"✂️ Cutting: {data['start']} for {data['duration']}s (Focus: {data['crop_focus']})")

        # 4. FFmpeg Processing
        stream = ffmpeg.input(raw_path, ss=data['start'], t=data['duration'])
        
        # Calculate Crop
        if data['crop_focus'] == 'left':
            x_crop = 0
        elif data['crop_focus'] == 'right':
            x_crop = "iw-ow"
        else:
            x_crop = "(iw-ow)/2" # Center
            
        stream = ffmpeg.filter(stream, 'crop', 'ih*(9/16)', 'ih', x_crop, 0)
        stream = ffmpeg.output(stream, final_path)
        ffmpeg.run(stream, overwrite_output=True, quiet=True)

        # 5. Upload to Drive
        print("☁️ Uploading to Drive...")
        drive_link = upload_to_drive(final_path, f"Short_{job_id}.mp4")

        # Cleanup
        genai.delete_file(video_file.name)
        os.remove(raw_path)
        os.remove(final_path)

        return {"status": "success", "link": drive_link, "metadata": data}

    except Exception as e:
        return {"status": "error", "message": str(e)}