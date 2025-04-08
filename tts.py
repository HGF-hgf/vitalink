import openai
import  os
import dotenv
dotenv.load_dotenv()

def generate_text_to_speech(text):
    try:
        openai.api_key = os.getenv("OPENAI_API_KEY")
        
        response = openai.audio.speech.create(
            model="tts-1",
            voice="alloy",  # Giọng đọc, có thể đổi thành "echo", "fable", "onyx", "nova", "shimmer"
            input=text
        )
        output_path = os.path.join("static", "speech.mp3")
        # Ghi file âm thanh
        with open(output_path, "wb") as audio_file:
            audio_file.write(response.content)
        
        print(f"🔊 File âm thanh đã lưu tại: {output_path}")
        return output_path
    except Exception as e:
        print(f"❌ Error: {e}")
        return None