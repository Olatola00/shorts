import os
import uuid
import yt_dlp
import logging

# Configure logging to keep track of what's happening
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class VideoDownloader:
    def __init__(self, download_dir="downloads"):
        self.download_dir = download_dir
        # Ensure the download directory exists
        if not os.path.exists(self.download_dir):
            os.makedirs(self.download_dir)

    def download_video(self, video_url: str) -> dict:
        """
        Downloads a video from YouTube using yt-dlp.
        Returns a dictionary with the file path and metadata.
        """
        try:
            # Generate a unique filename to avoid collisions
            unique_id = str(uuid.uuid4())
            output_template = os.path.join(self.download_dir, f"{unique_id}.%(ext)s")

            # yt-dlp options (Consistent with standard high-quality extraction)
            ydl_opts = {
                'format': 'bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
                'outtmpl': output_template,
                'quiet': True,
                'no_warnings': True,
            }

            logger.info(f"Starting download for URL: {video_url}")

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # Extract info first to get metadata
                info_dict = ydl.extract_info(video_url, download=True)
                
                # Get the actual filename created
                filename = ydl.prepare_filename(info_dict)
                
                # Retrieve video title and duration for the AI context later
                video_title = info_dict.get('title', 'Unknown Title')
                duration = info_dict.get('duration', 0)

            logger.info(f"Download successful: {filename}")

            return {
                "status": "success",
                "file_path": filename,
                "title": video_title,
                "duration": duration,
                "video_id": info_dict.get('id')
            }

        except Exception as e:
            logger.error(f"Download failed: {str(e)}")
            return {
                "status": "error",
                "message": str(e)
            }