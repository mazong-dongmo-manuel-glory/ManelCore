import os
import logging
import time
from pathlib import Path
import google.generativeai as genai

logger = logging.getLogger(__name__)

class TranscriptionService:
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.getenv("GOOGLE_API_KEY")
        if self.api_key:
            genai.configure(api_key=self.api_key)
        else:
            logger.warning("GOOGLE_API_KEY non configurée. Transcription désactivée.")

    async def transcribe(self, file_path: str) -> str:
        """Transcribe an audio file using Gemini 1.5 Flash."""
        if not self.api_key:
            return "[Erreur: Clé API Google manquante]"

        try:
            # Check if file exists
            path = Path(file_path)
            if not path.exists():
                return f"[Erreur: Fichier {file_path} introuvable]"

            # Use Gemini 1.5 Flash for audio processing
            # For short files (like Telegram voice notes), we can use the simple upload or direct content
            model = genai.GenerativeModel("gemini-1.5-flash")
            
            # Upload the file
            # Note: For small files < 20MB, we could potentially send directly, 
            # but uploading is more robust for Gemini.
            audio_file = genai.upload_file(path=file_path, mime_type="audio/ogg" if file_path.endswith(".oga") else None)
            
            # Wait for processing if necessary (usually instant for small files)
            # but for safety:
            while audio_file.state.name == "PROCESSING":
                time.sleep(1)
                audio_file = genai.get_file(audio_file.name)

            if audio_file.state.name == "FAILED":
                return "[Erreur: Échec du traitement audio par Gemini]"

            # Generate transcription
            prompt = "Retranscris cet audio en français. Si c'est une question, garde la ponctuation. Ne fais pas de résumé, juste la transcription fidèle."
            response = model.generate_content([prompt, audio_file])
            
            # Clean up: delete the file from Gemini servers
            genai.delete_file(audio_file.name)
            
            return response.text.strip()

        except Exception as exc:
            logger.error(f"Erreur transcription: {exc}")
            return f"[Erreur lors de la transcription: {exc}]"

_transcription_service = None

def get_transcription_service(api_key: str | None = None) -> TranscriptionService:
    global _transcription_service
    if _transcription_service is None:
        _transcription_service = TranscriptionService(api_key=api_key)
    return _transcription_service
