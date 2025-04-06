 
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from pymongo import MongoClient
import openai
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Dict
import json
import uvicorn
import uuid

mongo_client = MongoClient("mongodb+srv://ngvh1110:1234@cluster0.ff8rq.mongodb.net/")
db = mongo_client["Vitalink"]
collection = db["Chat_history"]

app = FastAPI()

class Message(BaseModel):
    message: str
    sender: str

class ChatRequest(BaseModel):
    message: str
    formData: dict = {}

class UserIdRequest(BaseModel):
    user_id: str

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
    return {key: value for key, value in form_data.items() if value and value.strip() != ""}

@app.websocket("/api/chat")
async def chat(websocket: WebSocket):
    await websocket.accept()
    websocket.formData = {}
    websocket.chat_history = []
    clients.append(websocket)
    
    try:
        while True:
            message = await websocket.receive_text()
            await handle_message(websocket, message)
    except WebSocketDisconnect:
        handle_disconnect(websocket)

async def handle_message(websocket: WebSocket, message: str):
    try:
        data = json.loads(message)
        
        if data.get("type") == "init" and not hasattr(websocket, "user_id"):
            user_id = str(uuid.uuid4())
            websocket.user_id = user_id

            filled_fields = get_filled_fields(websocket.formData)
            if not filled_fields:
                greeting = "Chào bạn! Tôi là chatbot hỗ trợ đăng ký khám bệnh. Bạn cần tôi giúp gì hôm nay?"
            else:
                filled_info = ", ".join([f"{key}: {value}" for key, value in filled_fields.items()])
                greeting = f"Chào bạn! Tôi thấy bạn đã điền {filled_info}. Bạn muốn tôi giúp gì tiếp theo?"
            websocket.chat_history.append(Message(message=greeting, sender="Bot"))
            await websocket.send_text(json.dumps({
                "user_id": user_id,
                "chat_history": [msg.dict() for msg in websocket.chat_history]
            }))
            collection.update_one(
                {"user_id": user_id},
                {"$set": {"chat_history": [msg.dict() for msg in websocket.chat_history]}},
                upsert=True
            )
        
        elif data.get("type") == "formUpdate":
            received_form_data = data.get("data", {})
            websocket.formData = merge_form_data(websocket.formData, {"form": received_form_data})
            filled_fields = get_filled_fields(websocket.formData)
            await websocket.send_text(json.dumps({"form": filled_fields}))
        
        elif data.get("type") == "chat" or "type" not in data:
            if not hasattr(websocket, "user_id"):
                user_id = str(uuid.uuid4())
                websocket.user_id = user_id
            websocket.chat_history.append(Message(message=data.get("message", message), sender="You"))
            await broadcast_messages(websocket)
            
            prompt = generate_prompt(websocket, data.get("message", message))
            response = get_response(prompt)
            print(f"Raw response: {response}")
            
            result = json.loads(response)
            websocket.formData = merge_form_data(websocket.formData, result)
            
            websocket.chat_history.append(Message(message=result["reply"], sender="Bot"))
            await send_final_form(websocket, websocket.formData, result)
            
            collection.update_one(
                {"user_id": websocket.user_id},
                {"$set": {"chat_history": [msg.dict() for msg in websocket.chat_history]}},
                upsert=True
            )
    
    except json.JSONDecodeError:
        if not hasattr(websocket, "user_id"):
            user_id = str(uuid.uuid4())
            websocket.user_id = user_id
        websocket.chat_history.append(Message(message=message, sender="You"))
        await broadcast_messages(websocket)
        
        prompt = generate_prompt(websocket, message)
        response = get_response(prompt)
        result = json.loads(response)
        websocket.formData = merge_form_data(websocket.formData, result)
        
        websocket.chat_history.append(Message(message=result["reply"], sender="Bot"))
        await send_final_form(websocket, websocket.formData, result)
        
        collection.update_one(
            {"user_id": websocket.user_id},
            {"$set": {"chat_history": [msg.dict() for msg in websocket.chat_history]}},
            upsert=True
        )
    except Exception as e:
        print(f"Error: {e}")
        await websocket.send_text(json.dumps({"reply": "Đã xảy ra lỗi, vui lòng thử lại."}))

async def broadcast_messages(websocket: WebSocket):
    await websocket.send_text(json.dumps({
        "user_id": websocket.user_id,
        "chat_history": [message.dict() for message in websocket.chat_history]
    }))

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
    ) if any(field in websocket.formData and websocket.formData[field] for field in all_required_fields) else "Chưa có thông tin nào được điền."

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
            f"Thông tin đã điền: {filled_info}\n"
            "Form đăng ký khám bệnh bao gồm các trường: "
            "Thông tin cá nhân: name (họ tên), dob (ngày sinh), gender (giới tính), cccd (số CCCD), province (tỉnh/thành), district (quận/huyện), ward (xã/phường), address (địa chỉ), phone (số điện thoại); "
            "Thông tin y tế: symptoms (triệu chứng), department (chuyên khoa khám). "
            f"Các trường còn thiếu: {', '.join(missing_field_labels) if missing_field_labels else 'không còn'}. "
            f"Nhiệm vụ: Phân tích câu của người dùng và trích xuất thông tin để điền vào trường '{next_field_label}'. "
            "Nếu không có thông tin cho '{next_field_label}', hãy trả lời tự nhiên bằng tiếng Việt để yêu cầu người dùng cung cấp, ví dụ: "
            "'Cảm ơn bạn đã cung cấp thông tin. Bạn có thể cho tôi biết {next_field_label} của bạn không?' hoặc "
            "'Dạ, tôi đã ghi nhận. Bạn vui lòng cho tôi biết thêm về {next_field_label} được không?' "
            "Nếu có thông tin, hãy xác nhận một cách tự nhiên, ví dụ: 'Oke, tôi đã ghi {next_field_label} là ...' "
            "Trả về kết quả dạng JSON với: "
            "'form' chứa các trường đã điền (chỉ cập nhật trường liên quan) và 'reply' chứa câu trả lời tự nhiên bằng tiếng Việt."
        )
    else:
        confirmation_message = (
            "Hình như mọi thông tin cần thiết đã được điền đầy đủ rồi! Đây là những gì tôi có:\n"
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
            "Bạn kiểm tra lại xem đúng hết chưa nhé? Nếu đúng thì nói 'có', còn nếu cần sửa thì cứ bảo tôi!"
        )
        return (
            f"Lịch sử chat:\n{chat_history_str}\n"
            f"Người dùng vừa nói: '{message}'. "
            f"Dữ liệu hiện tại của form: {websocket.formData}. "
            f"Thông tin đã điền: {filled_info}\n"
            "Form đăng ký khám bệnh bao gồm các trường: "
            "Thông tin cá nhân: name (họ tên), dob (ngày sinh), gender (giới tính), phone (số điện thoại), cccd (số CCCD), province (tỉnh/thành), district (quận/huyện), ward (xã/phường), address (địa chỉ); "
            "Thông tin y tế: symptoms (triệu chứng), department (chuyên khoa khám). "
            "Tất cả các trường đã được điền. "
            f"Hãy trả về JSON với 'form' chứa dữ liệu hiện tại và 'reply' là: '{confirmation_message}'."
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

@app.get("/api/history/{user_id}")
async def get_chat_history(user_id: str):
    chat_doc = collection.find_one({"user_id": user_id})
    if chat_doc and "chat_history" in chat_doc:
        return {"user_id": user_id, "chat_history": chat_doc["chat_history"]}
    else:
        raise HTTPException(status_code=404, detail="Không tìm thấy lịch sử chat cho user_id này.")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=5001)