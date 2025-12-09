import os
import logging
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DriveUploader:
    def __init__(self):
        # We load these from Environment Variables for security
        self.client_id = os.getenv("GOOGLE_CLIENT_ID")
        self.client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
        self.refresh_token = os.getenv("GOOGLE_REFRESH_TOKEN")
        
        # The specific folder in Google Drive to upload to (Optional)
        # If None, it uploads to the root folder.
        self.parent_folder_id = os.getenv("GOOGLE_DRIVE_FOLDER_ID")

        if not all([self.client_id, self.client_secret, self.refresh_token]):
            raise ValueError("Missing Google OAuth credentials in environment variables.")

        self.service = self._authenticate()

    def _authenticate(self):
        """
        Uses the Refresh Token to get a fresh Access Token automatically.
        """
        try:
            creds = Credentials(
                None, # Access token is None, we will refresh it
                refresh_token=self.refresh_token,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=self.client_id,
                client_secret=self.client_secret
            )
            return build('drive', 'v3', credentials=creds)
        except Exception as e:
            logger.error(f"Authentication failed: {str(e)}")
            raise

    def upload_file(self, file_path: str, video_title: str) -> dict:
        """
        Uploads a video to Google Drive and returns the public link.
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File to upload not found: {file_path}")

        try:
            file_name = os.path.basename(file_path)
            
            # File metadata
            file_metadata = {
                'name': f"{video_title} #Shorts", # Add #Shorts to help you identify it
                'mimeType': 'video/mp4'
            }
            
            # If a folder ID is set, place the file inside it
            if self.parent_folder_id:
                file_metadata['parents'] = [self.parent_folder_id]

            # Media content (Resumable uploads are safer for video)
            media = MediaFileUpload(
                file_path, 
                mimetype='video/mp4',
                resumable=True
            )

            logger.info(f"Starting upload: {file_name}")
            
            # Execute upload
            file = self.service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id, webViewLink'
            ).execute()

            logger.info(f"Upload complete. File ID: {file.get('id')}")

            return {
                "status": "success",
                "file_id": file.get('id'),
                "drive_link": file.get('webViewLink')
            }

        except Exception as e:
            logger.error(f"Google Drive Upload Failed: {str(e)}")
            return {
                "status": "error",
                "message": str(e)
            }