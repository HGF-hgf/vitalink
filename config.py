from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
import openai
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Dict
import json
import uvicorn

app = FastAPI()

class Message(BaseModel):
    message: str
    sender: str

class ChatRequest(BaseModel):
    message: str
    formData: dict = {}

# Danh sách các client WebSocket
clients: List[WebSocket] = []

# Khởi tạo OpenAI client (thay bằng key của bạn)
# openai.api_key =  "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"
  # Thay bằng key thực tế của bạn

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_response(question: str) -> str:
    try:
        response = openai.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "Bạn là một chatbot trợ giúp điền form đăng ký khám bệnh tại bệnh viện."},
                {"role": "user", "content": question}
            ]
        )
        return response.choices[0].message.content
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.websocket("/api/chat")
async def chat(websocket: WebSocket):
    await websocket.accept()
    # Gán thuộc tính cho WebSocket
    websocket.formData = {}
    websocket.chat_history = []  # Lịch sử chat riêng cho mỗi client
    clients.append(websocket)
    try:
        # Gửi lịch sử chat ban đầu (nếu có)
        await websocket.send_text(json.dumps([message.dict() for message in websocket.chat_history]))
        while True:
            message = await websocket.receive_text()
            if message == "refresh":
                websocket.chat_history = []  # Chỉ xóa lịch sử của client này
                await websocket.send_text(json.dumps([]))  # Gửi lịch sử rỗng về client
            else:
                await handle_message(websocket, message)
    except WebSocketDisconnect:
        handle_disconnect(websocket)

async def handle_message(websocket: WebSocket, message: str):
    # Thêm tin nhắn của người dùng vào lịch sử
    websocket.chat_history.append(Message(message=message, sender="You"))
    await broadcast_messages(websocket)
    
    # Tạo prompt với lịch sử chat
    prompt = generate_prompt(websocket, message)
    response = get_response(prompt)
    print(f"Raw response: {response}")
    
    # Phân tích phản hồi JSON từ bot
    result = json.loads(response)
    websocket.formData = merge_form_data(websocket.formData, result)
    
    # Thêm phản hồi của bot vào lịch sử
    websocket.chat_history.append(Message(message=result["reply"], sender="Bot"))
    await send_final_form(websocket, websocket.formData, result)

async def broadcast_messages(websocket: WebSocket):
    # Chỉ gửi lịch sử chat cho client hiện tại
    await websocket.send_text(json.dumps([message.dict() for message in websocket.chat_history]))

def generate_prompt(websocket: WebSocket, message: str) -> str:
    required_fields = ["name", "age", "phone", "symptoms", "department"]
    field_labels = {
        "name": "họ tên",
        "age": "tuổi",
        "phone": "số điện thoại",
        "symptoms": "triệu chứng",
        "department": "chuyên khoa khám"
    }
    missing_fields = [
        field for field in required_fields
        if field not in websocket.formData or not websocket.formData.get(field)
    ]
    missing_field_labels = [field_labels[field] for field in missing_fields]
    
    # Tạo lịch sử chat dưới dạng chuỗi
    chat_history_str = "\n".join([f"{msg.sender}: {msg.message}" for msg in websocket.chat_history])
    
    return (
        f"Lịch sử chat:\n{chat_history_str}\n"
        f"Người dùng vừa nói: '{message}'. "
        f"Dữ liệu hiện tại của form: {websocket.formData}. "
        "Form đăng ký khám bệnh bao gồm các trường: name (họ tên), age (tuổi), phone (số điện thoại), symptoms (triệu chứng), department (chuyên khoa khám). "
        f"Các trường còn thiếu thông tin là: {', '.join(missing_field_labels) if missing_field_labels else 'không có'}. "
        "Hãy phân tích câu của người dùng và trích xuất thông tin để điền vào các trường còn thiếu. "
        "Nếu người dùng không cung cấp đủ thông tin, hãy yêu cầu họ cung cấp thêm các trường còn thiếu. "
        "Nếu tất cả các trường đã được điền, hãy trả về thông báo xác nhận. "
        "Trả về kết quả dưới dạng JSON hợp lệ với hai phần: "
        "'form' chứa các trường đã điền và 'reply' chứa câu trả lời tự nhiên bằng tiếng Việt."
    )

def merge_form_data(form_data: dict, result: dict) -> dict:
    sanitized_form = {
        key: "" if value is None else value
        for key, value in result.get("form", {}).items()
    }
    return {**form_data, **sanitized_form}

async def send_final_form(websocket: WebSocket, final_form: dict, result: dict):
    await websocket.send_text(json.dumps({
        "form": final_form,
        "reply": result.get("reply", "Đã xử lý câu hỏi của bạn.")
    }))

def handle_disconnect(websocket: WebSocket):
    print(f"WebSocket disconnected: {websocket.client}")
    clients.remove(websocket)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=5001)