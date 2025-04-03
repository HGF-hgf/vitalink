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
# openai.api_key = "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"

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

def get_filled_fields(form_data: dict) -> dict:
    """Trả về một dictionary chỉ chứa các trường đã được điền (khác rỗng hoặc None)."""
    return {key: value for key, value in form_data.items() if value and value.strip() != ""}

@app.websocket("/api/chat")
async def chat(websocket: WebSocket):
    await websocket.accept()
    websocket.formData = {}
    websocket.chat_history = []  
    clients.append(websocket)
    try:
        await websocket.send_text(json.dumps([message.dict() for message in websocket.chat_history]))
        while True:
            message = await websocket.receive_text()
            if message == "refresh":
                websocket.chat_history = []  
                await websocket.send_text(json.dumps([]))  
            else:
                await handle_message(websocket, message)
    except WebSocketDisconnect:
        handle_disconnect(websocket)

async def handle_message(websocket: WebSocket, message: str):
    try:
        data = json.loads(message)
        
        if data.get("type") == "formUpdate":
            received_form_data = data.get("data", {})
            websocket.formData = merge_form_data(websocket.formData, {"form": received_form_data})
            filled_fields = get_filled_fields(websocket.formData)
            # Không gửi reply nếu không cần thiết
            await websocket.send_text(json.dumps({"form": filled_fields}))
        
        elif data.get("type") == "chat" or "type" not in data:
            websocket.chat_history.append(Message(message=data.get("message", message), sender="You"))
            await broadcast_messages(websocket)
            
            prompt = generate_prompt(websocket, data.get("message", message))
            response = get_response(prompt)
            print(f"Raw response: {response}")
            
            result = json.loads(response)
            websocket.formData = merge_form_data(websocket.formData, result)
            
            websocket.chat_history.append(Message(message=result["reply"], sender="Bot"))
            await send_final_form(websocket, websocket.formData, result)
    
    except json.JSONDecodeError:
        # Xử lý tin nhắn chat thông thường
        websocket.chat_history.append(Message(message=message, sender="You"))
        await broadcast_messages(websocket)
        
        prompt = generate_prompt(websocket, message)
        response = get_response(prompt)
        result = json.loads(response)
        websocket.formData = merge_form_data(websocket.formData, result)
        
        websocket.chat_history.append(Message(message=result["reply"], sender="Bot"))
        await send_final_form(websocket, websocket.formData, result)
    except Exception as e:
        print(f"Error: {e}")
        await websocket.send_text(json.dumps({"reply": "Đã xảy ra lỗi, vui lòng thử lại."}))
        
async def broadcast_messages(websocket: WebSocket):
    await websocket.send_text(json.dumps([message.dict() for message in websocket.chat_history]))

def generate_prompt(websocket: WebSocket, message: str) -> str:
    personal_fields = ["name", "dob", "gender", "cccd", "province", "district", "ward", "address", "phone"]
    medical_fields = ["symptoms", "department"]
    all_required_fields = personal_fields + medical_fields

    field_labels = {
        "name": "họ tên",
        "dob": "ngày sinh",
        "gender": "giới tính",
        "cccd": "số CCCD",
        "province": "tỉnh/thành",
        "district": "quận/huyện",
        "ward": "xã/phường",
        "address": "địa chỉ",
        "phone": "số điện thoại",
        "symptoms": "triệu chứng",
        "department": "chuyên khoa khám"
    }
    missing_personal = [field for field in personal_fields if field not in websocket.formData or not websocket.formData.get(field)]
    missing_medical = [field for field in medical_fields if field not in websocket.formData or not websocket.formData.get(field)]
    missing_field_labels = [field_labels[field] for field in (missing_personal + missing_medical)]

    chat_history_str = "\n".join([f"{msg.sender}: {msg.message}" for msg in websocket.chat_history])

    filled_info = "\n".join(
        [f"- {field_labels[field]}: {websocket.formData[field]}" for field in all_required_fields if field in websocket.formData and websocket.formData[field]]
    ) if any(field in websocket.formData and websocket.formData[field] for field in all_required_fields) else "Chưa có thông tin nào được điền sẵn."

    next_field = None
    next_field_label = None
    if missing_personal: 
        next_field = missing_personal[0]
        next_field_label = field_labels[next_field]
    elif missing_medical: 
        next_field = missing_medical[0]
        next_field_label = field_labels[next_field]

    if next_field:  
        return (
            f"Lịch sử chat:\n{chat_history_str}\n"
            f"Người dùng vừa nói: '{message}'. "
            f"Dữ liệu hiện tại của form: {websocket.formData}. "
            f"Thông tin đã điền sẵn:\n{filled_info}\n"
            "Form đăng ký khám bệnh bao gồm các trường: "
            "Thông tin cá nhân: name (họ tên), dob (ngày sinh), gender (giới tính), cccd (số CCCD), province (tỉnh/thành), district (quận/huyện), ward (xã/phường), address (địa chỉ), phone (số điện thoại); "
            "Thông tin y tế: symptoms (triệu chứng), department (chuyên khoa khám). "
            f"Các trường còn thiếu thông tin là: {', '.join(missing_field_labels) if missing_field_labels else 'không có'}. "
            f"Hãy phân tích câu của người dùng và trích xuất thông tin để điền vào trường '{next_field_label}'. "
            f"Nếu người dùng không cung cấp thông tin cho '{next_field_label}', hãy yêu cầu họ cung cấp thông tin đó. "
            "Trả về kết quả dưới dạng JSON hợp lệ với hai phần: "
            "'form' chứa các trường đã điền (chỉ cập nhật trường liên quan) và 'reply' chứa câu trả lời tự nhiên bằng tiếng Việt, bắt đầu bằng: 'Tôi thấy bạn đã điền: {filled_info}' nếu có thông tin điền sẵn."
        )
    else: 
        confirmation_message = (
            "Tất cả thông tin đã được điền. Dưới đây là thông tin bạn đã cung cấp:\n"
            f"- Họ tên: {websocket.formData.get('name', '')}\n"
            f"- Ngày sinh: {websocket.formData.get('dob', '')}\n"
            f"- Giới tính: {websocket.formData.get('gender', '')}\n"
            f"- Số CCCD: {websocket.formData.get('cccd', '')}\n"
            f"- Tỉnh/thành: {websocket.formData.get('province', '')}\n"
            f"- Quận/huyện: {websocket.formData.get('district', '')}\n"
            f"- Xã/phường: {websocket.formData.get('ward', '')}\n"
            f"- Địa chỉ: {websocket.formData.get('address', '')}\n"
            f"- Số điện thoại: {websocket.formData.get('phone', '')}\n"
            f"- Triệu chứng: {websocket.formData.get('symptoms', '')}\n"
            f"- Chuyên khoa khám: {websocket.formData.get('department', '')}\n"
            "Bạn có muốn xác nhận thông tin này không? (Trả lời 'có' hoặc 'không')"
        )
        return (
            f"Lịch sử chat:\n{chat_history_str}\n"
            f"Người dùng vừa nói: '{message}'. "
            f"Dữ liệu hiện tại của form: {websocket.formData}. "
            f"Thông tin đã điền sẵn:\n{filled_info}\n"
            "Form đăng ký khám bệnh bao gồm các trường: "
            "Thông tin cá nhân: name (họ tên), dob (ngày sinh), gender (giới tính), phone (số điện thoại), cccd (số CCCD), province (tỉnh/thành), district (quận/huyện), ward (xã/phường), address (địa chỉ); "
            "Thông tin y tế: symptoms (triệu chứng), department (chuyên khoa khám). "
            "Tất cả các trường đã được điền. "
            f"Hãy trả về câu trả lời dưới dạng JSON với 'form' chứa dữ liệu hiện tại và 'reply' là: '{confirmation_message}'."
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