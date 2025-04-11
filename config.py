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
    if not isinstance(form_data, dict):
        return {}
    
    filled = {}
    if all(isinstance(value, dict) for value in form_data.values()):
        for category, data in form_data.items():
            if not isinstance(data, dict):
                continue
            filled[category] = {key: value for key, value in data.items() if value and value.strip() != ""}
    else:
        filled = {key: value for key, value in form_data.items() if value and value.strip() != ""}
    return filled

@app.websocket("/api/chat")
async def chat(websocket: WebSocket):
    await websocket.accept()
    websocket.formData = {
        "personal": {},
        "medical": {},
        "symptom_details": {},
        "history": {},
        "family": {}
    }
    websocket.chat_history = []
    websocket.last_asked_field = None
    websocket.last_asked_category = None  # Thêm để theo dõi category hiện tại
    websocket.ask_count = 0
    websocket.last_message = None  # Lưu tin nhắn cuối cùng để tránh lặp
    clients.append(websocket)
    
    try:
        while True:
            message = await websocket.receive_text()
            if message != websocket.last_message:
                websocket.last_message = message
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
            if not any(filled_fields.values()):
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
            
            # Kiểm tra nếu form rỗng và đang hỏi lại cùng một trường
            current_field = websocket.last_asked_field
            current_category = websocket.last_asked_category
            next_field = None
            next_category = None

            if "form" in result and not any(result["form"].values()):  # Kiểm tra nếu form rỗng
                websocket.ask_count += 1
                print(f"Ask count: {websocket.ask_count}, Current field: {current_field}")
                if websocket.ask_count >= 3:
                    websocket.ask_count = 0
                    personal_fields = ["name", "dob", "gender", "cccd", "province", "district", "ward", "address", "phone", "symptoms"]  # Thêm symptoms vào personal
                    medical_fields = []  # Bỏ symptoms khỏi medical
                    symptom_detail_fields = ["site", "onset", "character", "radiation", "alleviating", "timing", "exacerbating", "severity", "previous_check"]
                    history_fields = ["position", "last", "occasion", "vadap", "cangay", "duration", "spread"]
                    family_fields = ["ditruyen", "last", "occasion", "vadap"]

                    missing_personal = [field for field in personal_fields if field not in websocket.formData["personal"] or not websocket.formData["personal"].get(field)]
                    missing_medical = [field for field in medical_fields if field not in websocket.formData["medical"] or not websocket.formData["medical"].get(field)]
                    missing_symptom_details = [field for field in symptom_detail_fields if field not in websocket.formData["symptom_details"] or not websocket.formData["symptom_details"].get(field)]
                    missing_history = [field for field in history_fields if field not in websocket.formData["history"] or not websocket.formData["history"].get(field)]
                    missing_family = [field for field in family_fields if field not in websocket.formData["family"] or not websocket.formData["family"].get(field)]

                    if missing_personal:
                        next_field = missing_personal[0] if missing_personal[0] != current_field else missing_personal[1] if len(missing_personal) > 1 else None
                        next_category = "personal"
                    elif missing_medical:
                        next_field = missing_medical[0] if missing_medical[0] != current_field else missing_medical[1] if len(missing_medical) > 1 else None
                        next_category = "medical"
                    elif missing_symptom_details and "symptoms" in websocket.formData["personal"] and websocket.formData["personal"]["symptoms"]:  # Sửa điều kiện để kiểm tra symptoms trong personal
                        next_field = missing_symptom_details[0] if missing_symptom_details[0] != current_field else missing_symptom_details[1] if len(missing_symptom_details) > 1 else None
                        next_category = "symptom_details"
                    elif missing_history:
                        next_field = missing_history[0] if missing_history[0] != current_field else missing_history[1] if len(missing_history) > 1 else None
                        next_category = "history"
                    elif missing_family:
                        next_field = missing_family[0] if missing_family[0] != current_field else missing_family[1] if len(missing_family) > 1 else None
                        next_category = "family"

                    if next_field:
                        field_labels = {
                            "name": "họ tên", "dob": "ngày sinh", "gender": "giới tính", "cccd": "số CCCD",
                            "province": "tỉnh/thành", "district": "quận/huyện", "ward": "xã/phường", "address": "địa chỉ",
                            "phone": "số điện thoại", "symptoms": "triệu chứng", "site": "vị trí triệu chứng",
                            "onset": "thời điểm khởi phát triệu chứng", "character": "tính chất triệu chứng",
                            "radiation": "triệu chứng lan tỏa hoặc kèm theo", "alleviating": "yếu tố làm giảm triệu chứng",
                            "timing": "thời gian và tần suất triệu chứng", "exacerbating": "yếu tố làm nặng triệu chứng",
                            "severity": "mức độ triệu chứng (1-10)", "previous_check": "đã khám ở đâu chưa trước đó với triệu chứng này",
                            "position": "bệnh lý đã mắc trước đó", "last": "phẫu thuật bao giờ chưa", "occasion": "dị ứng",
                            "vadap": "tiền sử dịch tễ", "cangay": "tiền sử thai sản, kinh nguyệt", "duration": "rượu bia, chất kích thích",
                            "spread": "thói quen sinh hoạt, chế độ ăn", "ditruyen": "gia đình có tiền sử bệnh nào có tính di truyền không",
                            "last": "xung quanh có tiền sử bệnh nào có tính di truyền không", "occasion": "gia đình có ai có bệnh lý nội khoa không",
                            "vadap": "hàng xóm có ai tiếp xúc mà có triệu chứng tương tự không"
                        }
                        # Gửi thông báo next nếu chuyển category
                        if current_category != next_category:
                            await websocket.send_text(json.dumps({
                                "type": "next",
                                "category": next_category
                            }))
                        result["reply"] = f"Hmm, có vẻ bạn chưa cung cấp thông tin về {field_labels[current_field]}. Không sao, chúng ta sẽ quay lại sau. Bạn có thể cho tôi biết {field_labels[next_field]} của bạn không?"
                        websocket.last_asked_field = next_field
                        websocket.last_asked_category = next_category
                    else:
                        result["reply"] = "Hình như bạn chưa cung cấp đủ thông tin, nhưng không sao, chúng ta sẽ quay lại sau. Bạn có muốn tiếp tục không?"
                        websocket.last_asked_field = None
                        websocket.last_asked_category = None
            else:
                websocket.ask_count = 0
                # Xác định current_field và current_category từ result["form"]
                current_field = None
                current_category = None
                for category in result["form"]:
                    for field in result["form"][category]:
                        current_field = field
                        current_category = category

                personal_fields = ["name", "dob", "gender", "cccd", "province", "district", "ward", "address", "phone", "symptoms"]  # Thêm symptoms vào personal
                medical_fields = []  # Bỏ symptoms khỏi medical
                symptom_detail_fields = ["site", "onset", "character", "radiation", "alleviating", "timing", "exacerbating", "severity", "previous_check"]
                history_fields = ["position", "last", "occasion", "vadap", "cangay", "duration", "spread"]
                family_fields = ["ditruyen", "last", "occasion", "vadap"]

                missing_personal = [field for field in personal_fields if field not in websocket.formData["personal"] or not websocket.formData["personal"].get(field)]
                missing_medical = [field for field in medical_fields if field not in websocket.formData["medical"] or not websocket.formData["medical"].get(field)]
                missing_symptom_details = [field for field in symptom_detail_fields if field not in websocket.formData["symptom_details"] or not websocket.formData["symptom_details"].get(field)]
                missing_history = [field for field in history_fields if field not in websocket.formData["history"] or not websocket.formData["history"].get(field)]
                missing_family = [field for field in family_fields if field not in websocket.formData["family"] or not websocket.formData["family"].get(field)]

                if missing_personal:
                    next_field = missing_personal[0]
                    next_category = "personal"
                elif missing_medical:
                    next_field = missing_medical[0]
                    next_category = "medical"
                elif missing_symptom_details and "symptoms" in websocket.formData["personal"] and websocket.formData["personal"]["symptoms"]:  # Sửa điều kiện để kiểm tra symptoms trong personal
                    next_field = missing_symptom_details[0]
                    next_category = "symptom_details"
                elif missing_history:
                    next_field = missing_history[0]
                    next_category = "history"
                elif missing_family:
                    next_field = missing_family[0]
                    next_category = "family"

                if next_field:
                    # Gửi thông báo next nếu chuyển category
                    if current_category != next_category:
                        await websocket.send_text(json.dumps({
                            "type": "next",
                            "category": next_category
                        }))
                    websocket.last_asked_field = next_field
                    websocket.last_asked_category = next_category

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
        
        current_field = websocket.last_asked_field
        current_category = websocket.last_asked_category
        next_field = None
        next_category = None

        if "form" in result and not any(result["form"].values()):
            websocket.ask_count += 1
            print(f"Ask count: {websocket.ask_count}, Current field: {current_field}")
            if websocket.ask_count >= 3:
                websocket.ask_count = 0
                personal_fields = ["name", "dob", "gender", "cccd", "province", "district", "ward", "address", "phone", "symptoms"]  # Thêm symptoms vào personal
                medical_fields = []  # Bỏ symptoms khỏi medical
                symptom_detail_fields = ["site", "onset", "character", "radiation", "alleviating", "timing", "exacerbating", "severity", "previous_check"]
                history_fields = ["position", "last", "occasion", "vadap", "cangay", "duration", "spread"]
                family_fields = ["ditruyen", "last", "occasion", "vadap"]

                missing_personal = [field for field in personal_fields if field not in websocket.formData["personal"] or not websocket.formData["personal"].get(field)]
                missing_medical = [field for field in medical_fields if field not in websocket.formData["medical"] or not websocket.formData["medical"].get(field)]
                missing_symptom_details = [field for field in symptom_detail_fields if field not in websocket.formData["symptom_details"] or not websocket.formData["symptom_details"].get(field)]
                missing_history = [field for field in history_fields if field not in websocket.formData["history"] or not websocket.formData["history"].get(field)]
                missing_family = [field for field in family_fields if field not in websocket.formData["family"] or not websocket.formData["family"].get(field)]

                if missing_personal:
                    next_field = missing_personal[0] if missing_personal[0] != current_field else missing_personal[1] if len(missing_personal) > 1 else None
                    next_category = "personal"
                elif missing_medical:
                    next_field = missing_medical[0] if missing_medical[0] != current_field else missing_medical[1] if len(missing_medical) > 1 else None
                    next_category = "medical"
                elif missing_symptom_details and "symptoms" in websocket.formData["personal"] and websocket.formData["personal"]["symptoms"]:  # Sửa điều kiện để kiểm tra symptoms trong personal
                    next_field = missing_symptom_details[0] if missing_symptom_details[0] != current_field else missing_symptom_details[1] if len(missing_symptom_details) > 1 else None
                    next_category = "symptom_details"
                elif missing_history:
                    next_field = missing_history[0] if missing_history[0] != current_field else missing_history[1] if len(missing_history) > 1 else None
                    next_category = "history"
                elif missing_family:
                    next_field = missing_family[0] if missing_family[0] != current_field else missing_family[1] if len(missing_family) > 1 else None
                    next_category = "family"

                if next_field:
                    field_labels = {
                        "name": "họ tên", "dob": "ngày sinh", "gender": "giới tính", "cccd": "số CCCD",
                        "province": "tỉnh/thành", "district": "quận/huyện", "ward": "xã/phường", "address": "địa chỉ",
                        "phone": "số điện thoại", "symptoms": "triệu chứng", "site": "vị trí triệu chứng",
                        "onset": "thời điểm khởi phát triệu chứng", "character": "tính chất triệu chứng",
                        "radiation": "triệu chứng lan tỏa hoặc kèm theo", "alleviating": "yếu tố làm giảm triệu chứng",
                        "timing": "thời gian và tần suất triệu chứng", "exacerbating": "yếu tố làm nặng triệu chứng",
                        "severity": "mức độ triệu chứng (1-10)", "previous_check": "đã khám ở đâu chưa trước đó với triệu chứng này",
                        "position": "bệnh lý đã mắc trước đó", "last": "phẫu thuật bao giờ chưa", "occasion": "dị ứng",
                        "vadap": "tiền sử dịch tễ", "cangay": "tiền sử thai sản, kinh nguyệt", "duration": "rượu bia, chất kích thích",
                        "spread": "thói quen sinh hoạt, chế độ ăn", "ditruyen": "gia đình có tiền sử bệnh nào có tính di truyền không",
                        "last": "xung quanh có tiền sử bệnh nào có tính di truyền không", "occasion": "gia đình có ai có bệnh lý nội khoa không",
                        "vadap": "hàng xóm có ai tiếp xúc mà có triệu chứng tương tự không"
                    }
                    # Gửi thông báo next nếu chuyển category
                    if current_category != next_category:
                        await websocket.send_text(json.dumps({
                            "type": "next",
                            "category": next_category
                        }))
                    result["reply"] = f"Hmm, có vẻ bạn chưa cung cấp thông tin về {field_labels[current_field]}. Không sao, chúng ta sẽ quay lại sau. Bạn có thể cho tôi biết {field_labels[next_field]} của bạn không?"
                    websocket.last_asked_field = next_field
                    websocket.last_asked_category = next_category
                else:
                    result["reply"] = "Hình như bạn chưa cung cấp đủ thông tin, nhưng không sao, chúng ta sẽ quay lại sau. Bạn có muốn tiếp tục không?"
                    websocket.last_asked_field = None
                    websocket.last_asked_category = None
        else:
            websocket.ask_count = 0
            # Xác định current_field và current_category từ result["form"]
            current_field = None
            current_category = None
            for category in result["form"]:
                for field in result["form"][category]:
                    current_field = field
                    current_category = category

            personal_fields = ["name", "dob", "gender", "cccd", "province", "district", "ward", "address", "phone", "symptoms"]  # Thêm symptoms vào personal
            medical_fields = []  # Bỏ symptoms khỏi medical
            symptom_detail_fields = ["site", "onset", "character", "radiation", "alleviating", "timing", "exacerbating", "severity", "previous_check"]
            history_fields = ["position", "last", "occasion", "vadap", "cangay", "duration", "spread"]
            family_fields = ["ditruyen", "last", "occasion", "vadap"]

            missing_personal = [field for field in personal_fields if field not in websocket.formData["personal"] or not websocket.formData["personal"].get(field)]
            missing_medical = [field for field in medical_fields if field not in websocket.formData["medical"] or not websocket.formData["medical"].get(field)]
            missing_symptom_details = [field for field in symptom_detail_fields if field not in websocket.formData["symptom_details"] or not websocket.formData["symptom_details"].get(field)]
            missing_history = [field for field in history_fields if field not in websocket.formData["history"] or not websocket.formData["history"].get(field)]
            missing_family = [field for field in family_fields if field not in websocket.formData["family"] or not websocket.formData["family"].get(field)]

            if missing_personal:
                next_field = missing_personal[0]
                next_category = "personal"
            elif missing_medical:
                next_field = missing_medical[0]
                next_category = "medical"
            elif missing_symptom_details and "symptoms" in websocket.formData["personal"] and websocket.formData["personal"]["symptoms"]:  # Sửa điều kiện để kiểm tra symptoms trong personal
                next_field = missing_symptom_details[0]
                next_category = "symptom_details"
            elif missing_history:
                next_field = missing_history[0]
                next_category = "history"
            elif missing_family:
                next_field = missing_family[0]
                next_category = "family"

            if next_field:
                # Gửi thông báo next nếu chuyển category
                if current_category != next_category:
                    await websocket.send_text(json.dumps({
                        "type": "next",
                        "category": next_category
                    }))
                websocket.last_asked_field = next_field
                websocket.last_asked_category = next_category

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
    personal_fields = ["name", "dob", "gender", "cccd", "province", "district", "ward", "address", "phone", "symptoms"]  # Thêm symptoms vào personal
    medical_fields = []  # Bỏ symptoms khỏi medical
    symptom_detail_fields = [
        "site", "onset", "character", "radiation", "alleviating", 
        "timing", "exacerbating", "severity", "previous_check"
    ]
    history_fields = ["position", "last", "occasion", "vadap", "cangay", "duration", "spread"]
    family_fields = ["ditruyen", "last", "occasion", "vadap"]

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
        "site": "vị trí triệu chứng",
        "onset": "thời điểm khởi phát triệu chứng",
        "character": "tính chất triệu chứng",
        "radiation": "triệu chứng lan tỏa hoặc kèm theo",
        "alleviating": "yếu tố làm giảm triệu chứng",
        "timing": "thời gian và tần suất triệu chứng",
        "exacerbating": "yếu tố làm nặng triệu chứng",
        "severity": "mức độ triệu chứng (1-10)",
        "previous_check": "đã khám ở đâu chưa trước đó với triệu chứng này",
        "position": "bệnh lý đã mắc trước đó",
        "last": "phẫu thuật bao giờ chưa",
        "occasion": "dị ứng",
        "vadap": "tiền sử dịch tễ",
        "cangay": "tiền sử thai sản, kinh nguyệt",
        "duration": "rượu bia, chất kích thích",
        "spread": "thói quen sinh hoạt, chế độ ăn",
        "ditruyen": "gia đình có tiền sử bệnh nào có tính di truyền không",
        "last": "xung quanh có tiền sử bệnh nào có tính di truyền không",
        "occasion": "gia đình có ai có bệnh lý nội khoa không",
        "vadap": "hàng xóm có ai tiếp xúc mà có triệu chứng tương tự không"
    }

    missing_personal = [field for field in personal_fields if field not in websocket.formData["personal"] or not websocket.formData["personal"].get(field)]
    missing_medical = [field for field in medical_fields if field not in websocket.formData["medical"] or not websocket.formData["medical"].get(field)]
    missing_symptom_details = [field for field in symptom_detail_fields if field not in websocket.formData["symptom_details"] or not websocket.formData["symptom_details"].get(field)]
    missing_history = [field for field in history_fields if field not in websocket.formData["history"] or not websocket.formData["history"].get(field)]
    missing_family = [field for field in family_fields if field not in websocket.formData["family"] or not websocket.formData["family"].get(field)]

    chat_history_str = "\n".join([f"{msg.sender}: {msg.message}" for msg in websocket.chat_history])

    filled_info = "\n".join(
        [f"- {field_labels[field]}: {websocket.formData['personal'][field]}" for field in personal_fields if field in websocket.formData["personal"] and websocket.formData["personal"][field]] +
        [f"- {field_labels[field]}: {websocket.formData['medical'][field]}" for field in medical_fields if field in websocket.formData["medical"] and websocket.formData["medical"][field]] +
        [f"- {field_labels[field]}: {websocket.formData['symptom_details'][field]}" for field in symptom_detail_fields if field in websocket.formData["symptom_details"] and websocket.formData["symptom_details"][field]] +
        [f"- {field_labels[field]}: {websocket.formData['history'][field]}" for field in history_fields if field in websocket.formData["history"] and websocket.formData["history"][field]] +
        [f"- {field_labels[field]}: {websocket.formData['family'][field]}" for field in family_fields if field in websocket.formData["family"] and websocket.formData["family"][field]]
    ) if any(
        field in websocket.formData["personal"] and websocket.formData["personal"][field] for field in personal_fields
    ) or any(
        field in websocket.formData["medical"] and websocket.formData["medical"][field] for field in medical_fields
    ) or any(
        field in websocket.formData["symptom_details"] and websocket.formData["symptom_details"][field] for field in symptom_detail_fields
    ) or any(
        field in websocket.formData["history"] and websocket.formData["history"][field] for field in history_fields
    ) or any(
        field in websocket.formData["family"] and websocket.formData["family"][field] for field in family_fields
    ) else "Chưa có thông tin nào được điền."

    missing_field_labels = (
        [field_labels[field] for field in missing_personal] +
        [field_labels[field] for field in missing_medical] +
        [field_labels[field] for field in missing_symptom_details] +
        [field_labels[field] for field in missing_history] +
        [field_labels[field] for field in missing_family]
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
    elif missing_symptom_details and "symptoms" in websocket.formData["personal"] and websocket.formData["personal"]["symptoms"]:  # Sửa điều kiện để kiểm tra symptoms trong personal
        next_field = missing_symptom_details[0]
        next_field_label = field_labels[next_field]
        next_category = "symptom_details"
    elif missing_history:
        next_field = missing_history[0]
        next_field_label = field_labels[next_field]
        next_category = "history"
    elif missing_family:
        next_field = missing_family[0]
        next_field_label = field_labels[next_field]
        next_category = "family"

    if next_field:
        return (
            f"Lịch sử chat:\n{chat_history_str}\n"
            f"Người dùng vừa nói: '{message}'. "
            f"Dữ liệu hiện tại của form: {websocket.formData}. "
            f"Thông tin đã điền: {filled_info}\n"
            "Form đăng ký khám bệnh bao gồm:\n"
            "- Thông tin cá nhân: name (họ tên), dob (ngày sinh), gender (giới tính), cccd (số CCCD), province (tỉnh/thành), district (quận/huyện), ward (xã/phường), address (địa chỉ), phone (số điện thoại), symptoms (triệu chứng)\n"
            "- Thông tin y tế: không có\n"  # Bỏ symptoms khỏi medical
            "- Chi tiết triệu chứng: site (vị trí), onset (thời điểm khởi phát), character (tính chất), radiation (lan tỏa/kèm theo), alleviating (yếu tố làm giảm), timing (thời gian/tần suất), exacerbating (yếu tố làm nặng), severity (mức độ 1-10), previous_check (đã từng khám triệu chứng này ở đâu trước đó chưa)\n"
            "- Tiền sử bệnh: position (bệnh lý đã mắc trước đó), last (phẫu thuật bao giờ chưa), occasion (dị ứng), vadap (tiền sử dịch tễ), cangay (tiền sử thai sản, kinh nguyệt), duration (rượu bia, chất kích thích), spread (thói quen sinh hoạt, chế độ ăn)\n"
            "- Tiền sử gia đình: ditruyen (gia đình có tiền sử bệnh nào có tính di truyền không), last (xung quanh có tiền sử bệnh nào có tính di truyền không), occasion (gia đình có ai có bệnh lý nội khoa không), vadap (hàng xóm có ai tiếp xúc mà có triệu chứng tương tự không)\n"
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
            f"- Triệu chứng: {websocket.formData['personal'].get('symptoms', '')}\n"  # Sửa để lấy symptoms từ personal
            f"- Vị trí triệu chứng: {websocket.formData['symptom_details'].get('site', '')}\n"
            f"- Thời điểm khởi phát: {websocket.formData['symptom_details'].get('onset', '')}\n"
            f"- Tính chất: {websocket.formData['symptom_details'].get('character', '')}\n"
            f"- Lan tỏa/kèm theo: {websocket.formData['symptom_details'].get('radiation', '')}\n"
            f"- Yếu tố làm giảm: {websocket.formData['symptom_details'].get('alleviating', '')}\n"
            f"- Thời gian/tần suất: {websocket.formData['symptom_details'].get('timing', '')}\n"
            f"- Yếu tố làm nặng: {websocket.formData['symptom_details'].get('exacerbating', '')}\n"
            f"- Mức độ (1-10): {websocket.formData['symptom_details'].get('severity', '')}\n"
            f"- Đã từng khám triệu chứng này ở đâu chưa: {websocket.formData['symptom_details'].get('previous_check', '')}\n"
            f"- Bệnh lý đã mắc trước đó: {websocket.formData['history'].get('position', '')}\n"
            f"- Phẫu thuật bao giờ chưa: {websocket.formData['history'].get('last', '')}\n"
            f"- Dị ứng: {websocket.formData['history'].get('occasion', '')}\n"
            f"- Tiền sử dịch tễ: {websocket.formData['history'].get('vadap', '')}\n"
            f"- Tiền sử thai sản, kinh nguyệt: {websocket.formData['history'].get('cangay', '')}\n"
            f"- Rượu bia, chất kích thích: {websocket.formData['history'].get('duration', '')}\n"
            f"- Thói quen sinh hoạt, chế độ ăn: {websocket.formData['history'].get('spread', '')}\n"
            f"- Gia đình có tiền sử bệnh nào có tính di truyền không: {websocket.formData['family'].get('ditruyen', '')}\n"
            f"- Xung quanh có tiền sử bệnh nào có tính di truyền không: {websocket.formData['family'].get('last', '')}\n"
            f"- Gia đình có ai có bệnh lý nội khoa không: {websocket.formData['family'].get('occasion', '')}\n"
            f"- Hàng xóm có ai tiếp xúc mà có triệu chứng tương tự không: {websocket.formData['family'].get('vadap', '')}\n"
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
    
    for category in ["personal", "medical", "symptom_details", "history", "family"]:
        if category in new_form:
            if not isinstance(new_form[category], dict):
                continue
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