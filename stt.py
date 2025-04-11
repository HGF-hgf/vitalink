import openai
import os
import dotenv
import assemblyai as aai
# Load environment variables from .env file
dotenv.load_dotenv()


aai.settings.api_key = os.getenv("ASSEMBLY_API_KEY")
transcribe = aai.Transcriber()
def transcribe_audio_assemblyai(audio_path):
    try:
        transcript = transcribe.transcribe(audio_path)
        return transcript.text # Lấy nội dung văn bản
    except Exception as e:
        print(f"Error: {e}")
        return None

def transcribe_audio(audio_path):
    try:
        openai.api_key = os.getenv("OPENAI_API_KEY")
        with open(audio_path, "rb") as audio_file:
            response = openai.audio.transcriptions.create(model="whisper-1", file=audio_file, response_format="text")
        
        return response # Lấy nội dung văn bản
    except Exception as e:
        print(f"Error: {e}")
        return None

print(transcribe_audio_assemblyai("/home/nguyen-hoang/vitalink/vitalink/static/speech.mp3"))
# print(transcribe_audio("/home/nguyen-hoang/vitalink/vitalink/static/speech.mp3"))
