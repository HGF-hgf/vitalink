import openai
import os
import dotenv
# Load environment variables from .env file
dotenv.load_dotenv()




def transcribe_audio(audio_path):
    try:
        openai.api_key = os.getenv("OPENAI_API_KEY")
        with open(audio_path, "rb") as audio_file:
            response = openai.audio.transcriptions.create(model="whisper-1", file=audio_file, response_format="text")
        
        return response # Lấy nội dung văn bản
    except Exception as e:
        print(f"Error: {e}")
        return None
