from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from pymongo import MongoClient
import openai
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Dict
import json
import uvicorn
import uuid
from test import get_search_results
import os
from dotenv import load_dotenv
load_dotenv()

mongo_client = MongoClient(os.getenv("MONGODB_URI"))
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

class SubmitRequest(BaseModel):
    user_id: str
    symptoms: str

# Danh sách các client WebSocket
clients: List[WebSocket] = []

# Khởi tạo OpenAI client (thay bằng key của bạn)
openai.api_key = os.getenv("OPENAI_API_KEY")

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
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Bạn là một chatbot hỗ trợ điền form đăng ký khám bệnh tại bệnh viện. "
                        "Mọi phản hồi của bạn phải là một chuỗi JSON hợp lệ với hai trường: "
                        "'form' (object chứa thông tin form được cập nhật) và 'reply' (chuỗi chứa câu trả lời tự nhiên bằng tiếng Việt). "
                        "Ví dụ: {\"form\": {\"personal\": {\"name\": \"Nguyễn Văn A\"}}, \"reply\": \"Oke, tôi đã ghi họ tên là Nguyễn Văn A.\"}. "
                        "Không bao giờ trả về văn bản thông thường ngoài JSON."
                    )
                },
                {"role": "user", "content": question}
            ]
        )
        return response.choices[0].message.content
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def get_filled_fields(form_data: dict) -> dict:
    # Kiểm tra nếu form_data không phải là dictionary
    if not isinstance(form_data, dict):
        return {}
    
    filled = {}
    # Nếu form_data là dictionary lồng (có các category như personal, medical, symptom_details)
    if all(isinstance(value, dict) for value in form_data.values()):
        for category, data in form_data.items():
            if not isinstance(data, dict):
                continue
            filled[category] = {key: value for key, value in data.items() if value and value.strip() != ""}
    else:
        # Nếu form_data là dictionary phẳng
        filled = {key: value for key, value in form_data.items() if value and value.strip() != ""}
    return filled

@app.websocket("/api/chat")
async def chat(websocket: WebSocket):
    await websocket.accept()
    # Khởi tạo formData với các phần riêng biệt
    websocket.formData = {
        "personal": {},
        "medical": {},
        "symptom_details": {}
    }
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
            if not any(filled_fields.values()):  # Kiểm tra nếu không có trường nào được điền
                greeting = "Chào bạn! Tôi là chatbot hỗ trợ đăng ký khám bệnh. Bạn cần tôi giúp gì hôm nay?"
            else:
                filled_info = ", ".join([f"{key}: {value}" for category in filled_fields for key, value in filled_fields[category].items()])
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
            websocket.user_id = data.get("user_id")
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
    # Form riêng cho chi tiết triệu chứng (SOCRATES)
    symptom_detail_fields = [
        "site", "onset", "character", "radiation", "alleviating", 
        "timing", "exacerbating", "severity"
    ]

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
        "department": "chuyên khoa khám",
        "site": "vị trí triệu chứng",
        "onset": "thời điểm khởi phát triệu chứng",
        "character": "tính chất triệu chứng",
        "radiation": "triệu chứng lan tỏa hoặc kèm theo",
        "alleviating": "yếu tố làm giảm triệu chứng",
        "timing": "thời gian và tần suất triệu chứng",
        "exacerbating": "yếu tố làm nặng triệu chứng",
        "severity": "mức độ triệu chứng (1-10)"
    }

    missing_personal = [field for field in personal_fields if field not in websocket.formData["personal"] or not websocket.formData["personal"].get(field)]
    missing_medical = [field for field in medical_fields if field not in websocket.formData["medical"] or not websocket.formData["medical"].get(field)]
    missing_symptom_details = [field for field in symptom_detail_fields if field not in websocket.formData["symptom_details"] or not websocket.formData["symptom_details"].get(field)]

    chat_history_str = "\n".join([f"{msg.sender}: {msg.message}" for msg in websocket.chat_history])

    filled_info = "\n".join(
        [f"- {field_labels[field]}: {websocket.formData['personal'][field]}" for field in personal_fields if field in websocket.formData["personal"] and websocket.formData["personal"][field]] +
        [f"- {field_labels[field]}: {websocket.formData['medical'][field]}" for field in medical_fields if field in websocket.formData["medical"] and websocket.formData["medical"][field]] +
        [f"- {field_labels[field]}: {websocket.formData['symptom_details'][field]}" for field in symptom_detail_fields if field in websocket.formData["symptom_details"] and websocket.formData["symptom_details"][field]]
    ) if any(
        field in websocket.formData["personal"] and websocket.formData["personal"][field] for field in personal_fields
    ) or any(
        field in websocket.formData["medical"] and websocket.formData["medical"][field] for field in medical_fields
    ) or any(
        field in websocket.formData["symptom_details"] and websocket.formData["symptom_details"][field] for field in symptom_detail_fields
    ) else "Chưa có thông tin nào được điền."

    missing_field_labels = (
        [field_labels[field] for field in missing_personal] +
        [field_labels[field] for field in missing_medical] +
        [field_labels[field] for field in missing_symptom_details]
    )

    next_field = None
    next_field_label = None
    next_category = None

    if missing_personal:
        next_field = missing_personal[0]
        next_field_label = field_labels[next_field]
        next_category = "personal"
    elif missing_medical:
        next_field = missing_medical[0]
        next_field_label = field_labels[next_field]
        next_category = "medical"
    elif missing_symptom_details and "symptoms" in websocket.formData["medical"] and websocket.formData["medical"]["symptoms"]:
        next_field = missing_symptom_details[0]
        next_field_label = field_labels[next_field]
        next_category = "symptom_details"

    if next_field:
        return (
            f"Lịch sử chat:\n{chat_history_str}\n"
            f"Người dùng vừa nói: '{message}'. "
            f"Dữ liệu hiện tại của form: {websocket.formData}. "
            f"Thông tin đã điền: {filled_info}\n"
            "Form đăng ký khám bệnh bao gồm:\n"
            "- Thông tin cá nhân: name (họ tên), dob (ngày sinh), gender (giới tính), cccd (số CCCD), province (tỉnh/thành), district (quận/huyện), ward (xã/phường), address (địa chỉ), phone (số điện thoại)\n"
            "- Thông tin y tế: symptoms (triệu chứng), department (chuyên khoa khám)\n"
            "- Chi tiết triệu chứng: site (vị trí), onset (thời điểm khởi phát), character (tính chất), radiation (lan tỏa/kèm theo), alleviating (yếu tố làm giảm), timing (thời gian/tần suất), exacerbating (yếu tố làm nặng), severity (mức độ 1-10)\n"
            f"Các trường còn thiếu: {', '.join(missing_field_labels) if missing_field_labels else 'không còn'}. "
            f"Nhiệm vụ: Phân tích câu của người dùng và trích xuất thông tin để điền vào trường '{next_field_label}' (thuộc '{next_category}'). "
            "Nếu không có thông tin cho '{next_field_label}', trả lời tự nhiên bằng tiếng Việt để yêu cầu người dùng cung cấp, ví dụ: "
            "'Cảm ơn bạn đã cung cấp thông tin. Bạn có thể cho tôi biết {next_field_label} của bạn không?' hoặc "
            "'Dạ, tôi đã ghi nhận. Bạn vui lòng cho tôi biết thêm về {next_field_label} được không?' "
            "Nếu có thông tin, xác nhận tự nhiên, ví dụ: 'Oke, tôi đã ghi {next_field_label} là ...' "
            "Trả về kết quả dạng JSON với: "
            "'form' chứa các trường đã điền (chỉ cập nhật trường liên quan trong đúng category) và 'reply' chứa câu trả lời tự nhiên bằng tiếng Việt.\n"
            "Ví dụ:\n"
            "1. Tin nhắn: 'Tên tôi là Nguyễn Văn A' -> {\"form\": {\"personal\": {\"name\": \"Nguyễn Văn A\"}}, \"reply\": \"Oke, tôi đã ghi họ tên là Nguyễn Văn A.\"}\n"
            "2. Tin nhắn: 'Đau ở trán' -> {\"form\": {\"symptom_details\": {\"site\": \"trán\"}}, \"reply\": \"Oke, tôi đã ghi vị trí triệu chứng là trán.\"}\n"
            "3. Tin nhắn: 'Tôi không biết' -> {\"form\": {}, \"reply\": \"Cảm ơn bạn. Bạn có thể cho tôi biết {next_field_label} không?\"}"
        )
    else:
        confirmation_message = (
            "Hình như mọi thông tin cần thiết đã được điền đầy đủ rồi! Đây là những gì tôi có:\n"
            f"- Họ tên: {websocket.formData['personal'].get('name', '')}\n"
            f"- Ngày sinh: {websocket.formData['personal'].get('dob', '')}\n"
            f"- Giới tính: {websocket.formData['personal'].get('gender', '')}\n"
            f"- Số CCCD: {websocket.formData['personal'].get('cccd', '')}\n"
            f"- Tỉnh/thành: {websocket.formData['personal'].get('province', '')}\n"
            f"- Quận/huyện: {websocket.formData['personal'].get('district', '')}\n"
            f"- Xã/phường: {websocket.formData['personal'].get('ward', '')}\n"
            f"- Địa chỉ: {websocket.formData['personal'].get('address', '')}\n"
            f"- Số điện thoại: {websocket.formData['personal'].get('phone', '')}\n"
            f"- Triệu chứng: {websocket.formData['medical'].get('symptoms', '')}\n"
            f"- Chuyên khoa khám: {websocket.formData['medical'].get('department', '')}\n"
            f"- Vị trí triệu chứng: {websocket.formData['symptom_details'].get('site', '')}\n"
            f"- Thời điểm khởi phát: {websocket.formData['symptom_details'].get('onset', '')}\n"
            f"- Tính chất: {websocket.formData['symptom_details'].get('character', '')}\n"
            f"- Lan tỏa/kèm theo: {websocket.formData['symptom_details'].get('radiation', '')}\n"
            f"- Yếu tố làm giảm: {websocket.formData['symptom_details'].get('alleviating', '')}\n"
            f"- Thời gian/tần suất: {websocket.formData['symptom_details'].get('timing', '')}\n"
            f"- Yếu tố làm nặng: {websocket.formData['symptom_details'].get('exacerbating', '')}\n"
            f"- Mức độ (1-10): {websocket.formData['symptom_details'].get('severity', '')}\n"
            "Bạn kiểm tra lại xem đúng hết chưa nhé? Nếu đúng thì nói 'có', còn nếu cần sửa thì cứ bảo tôi!"
        )
        return (
            f"Lịch sử chat:\n{chat_history_str}\n"
            f"Người dùng vừa nói: '{message}'. "
            f"Dữ liệu hiện tại của form: {websocket.formData}. "
            f"Thông tin đã điền: {filled_info}\n"
            "Tất cả các trường đã được điền.\n"
            f"Hãy trả về JSON với 'form' chứa dữ liệu hiện tại và 'reply' là: '{confirmation_message}'."
        )

def merge_form_data(form_data: dict, result: dict) -> dict:
    new_form = result.get("form", {})
    updated_form = form_data.copy()
    
    for category in ["personal", "medical", "symptom_details"]:
        if category in new_form:
            # Kiểm tra nếu new_form[category] không phải là dictionary
            if not isinstance(new_form[category], dict):
                continue  # Bỏ qua nếu không phải dictionary
            if category not in updated_form:
                updated_form[category] = {}
            updated_form[category].update({
                key: "" if value is None else value
                for key, value in new_form[category].items()
            })
    
    return updated_form

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

@app.post("/api/submit_tests")
async def submit_tests(request: SubmitRequest):
    user_id = request.user_id
    symptoms = request.symptoms

    test_list = get_search_results(symptoms)
    test_list_array = [test.strip() for test in test_list.split("\n") if test.strip()]  

    for client in clients:
        if hasattr(client, "user_id") and client.user_id == user_id:
            reply = f"Dựa trên triệu chứng '{symptoms}', tôi đề xuất các xét nghiệm sau:\n" + "\n".join([f"- {test}" for test in test_list_array]) + "\nBạn muốn tôi giải thích thêm về xét nghiệm nào không?"
            client.chat_history.append(Message(message=reply, sender="Bot"))
            await client.send_text(json.dumps({
                "user_id": user_id,
                "chat_history": [msg.dict() for msg in client.chat_history],
                "tests": test_list_array  
            }))
            collection.update_one(
                {"user_id": user_id},
                {"$set": {"chat_history": [msg.dict() for msg in client.chat_history]}},
                upsert=True
            )
            break
    else:
        raise HTTPException(status_code=404, detail="Không tìm thấy kết nối WebSocket cho user_id này.")

    return {"user_id": user_id, "tests": test_list_array}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=5001)