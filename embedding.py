app.mount("/static", StaticFiles(directory=r"D:\Workspace\Temps\tech\EchoAds\Chatbot\static"), name="static")

class SpeechRequest(BaseModel):
    text: str
@app.post("/voice-query/")
async def voice_query(audio: UploadFile = File(...)):
    # Lưu file tạm thời
    temp_audio_path = f"temp_{audio.filename}"
    with open(temp_audio_path, "wb") as buffer:
        buffer.write(await audio.read())

    # Chuyển đổi giọng nói thành văn bản
    text_query = transcribe_audio(temp_audio_path)
    os.remove(temp_audio_path)  # Xóa file sau khi xử lý
    print("Transcribed text:", text_query)

    # Thêm câu hỏi vào lịch sử hội thoại
    messages.append(Message(message=text_query, sender="You"))

    # Nhận phản hồi từ chatbot (giữ ngữ cảnh)
    response = get_response(text_query)
    
    print(str(response))
    # Thêm phản hồi từ bot vào lịch sử chat
    messages.append(Message(message=response, sender="Bot"))

    # Cập nhật WebSocket clients với tin nhắn mới
    for client in clients:
        await client.send_text(json.dumps([msg.dict() for msg in messages]))

    # Tạo file âm thanh từ phản hồi chatbot
    audio_file_path = generate_text_to_speech(str(response))
    timestamp = int(datetime.now().timestamp())

    response_data = {
        "transcribed_text": text_query,
        "response": str(response),
        "audio_file": f"static/speech.mp3?{timestamp}" if audio_file_path else None  
    }
    
    return Response(
        content=json.dumps(response_data),
        media_type="application/json",
        headers={
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'self'",
            "Access-Control-Allow-Origin": "*"
        }
    )
