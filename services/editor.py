import os
import subprocess
import json
import logging
import uuid

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class VideoEditor:
    def __init__(self, output_dir="processed"):
        self.output_dir = output_dir
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)

    def get_video_info(self, file_path):
        """
        Uses ffprobe to get video dimensions.
        """
        cmd = [
            "ffprobe", 
            "-v", "error", 
            "-select_streams", "v:0", 
            "-show_entries", "stream=width,height", 
            "-of", "json", 
            file_path
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            info = json.loads(result.stdout)
            width = int(info['streams'][0]['width'])
            height = int(info['streams'][0]['height'])
            return width, height
        except Exception as e:
            logger.error(f"Error getting video info: {e}")
            raise

    def process_video(self, file_path: str, start_time: str, end_time: str) -> dict:
        """
        Cuts the video and ensures it is vertical (9:16).
        """
        try:
            # Generate output filename
            unique_id = str(uuid.uuid4())
            output_path = os.path.join(self.output_dir, f"{unique_id}_short.mp4")
            
            # 1. Analyze Input Dimensions
            width, height = self.get_video_info(file_path)
            logger.info(f"Input Dimensions: {width}x{height}")
            
            is_vertical = height > width
            
            # 2. Build FFmpeg Command
            # Base command: input file, start time, end time
            cmd = [
                "ffmpeg",
                "-y",               # Overwrite output file if exists
                "-i", file_path,
                "-ss", start_time,
                "-to", end_time,
                "-c:v", "libx264",  # Re-encode video
		"-crf", "18",
		"-preset", "slow",
                "-c:a", "aac",      # Re-encode audio
                "-strict", "experimental",
                "-b:a", "192k"      # Audio bitrate
            ]

            # 3. Add Crop Filters if needed
            if is_vertical:
                logger.info("Video is already vertical. No cropping needed.")
                # We still re-encode to ensure the cut is precise
            else:
                logger.info("Video is horizontal. Applying 9:16 center crop.")
                # FIX: Use 'ih' (Input Height) instead of invalid 'qh'
                # Logic: 
                # w = ih*(9/16) -> Width is 9/16th of height
                # h = ih        -> Height stays the same
                # x = (iw-ow)/2 -> Center the crop horizontally
                # y = 0         -> Start from top
                
                # We also use 'trunc(...)*2' to ensure width is an even number (required by libx264)
                crop_filter = f"crop=trunc(ih*9/16/2)*2:ih:(iw-ow)/2:0"
                cmd.extend(["-vf", crop_filter])

            # Add output path
            cmd.append(output_path)

            # 4. Run FFmpeg
            logger.info(f"Running FFmpeg command: {' '.join(cmd)}")
            subprocess.run(cmd, check=True)

            if not os.path.exists(output_path):
                raise FileNotFoundError("FFmpeg finished but output file is missing.")

            logger.info(f"Processing complete: {output_path}")

            return {
                "status": "success",
                "file_path": output_path
            }

        except subprocess.CalledProcessError as e:
            logger.error(f"FFmpeg failed: {e}")
            return {"status": "error", "message": "Video processing failed during encoding."}
        except Exception as e:
            logger.error(f"Editor failed: {str(e)}")
            return {"status": "error", "message": str(e)}