from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import openai
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# openai.api_key = "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"

class ChatRequest(BaseModel):
    message: str
    formData: dict = {}  

@app.post("/api/chat")
async def chat(request: ChatRequest):
    try:
        # Xác định các trường còn thiếu
        required_fields = ["hoTen", "tuoi", "soDienThoai", "trieuChung", "chuyenKhoa"]
        field_labels = {
            "hoTen": "họ tên",
            "tuoi": "tuổi",
            "soDienThoai": "số điện thoại",
            "trieuChung": "triệu chứng",
            "chuyenKhoa": "chuyên khoa khám"
        }
        missing_fields = [
            field for field in required_fields
            if field not in request.formData or not request.formData.get(field)
        ]
        missing_field_labels = [field_labels[field] for field in missing_fields]
        prompt = (
            f"Người dùng nói: '{request.message}'. "
            f"Dữ liệu hiện tại của form: {request.formData}. "
            "Form đăng ký khám bệnh bao gồm các trường: hoTen (họ tên), tuoi (tuổi), soDienThoai (số điện thoại), trieuChung (triệu chứng), chuyenKhoa (chuyên khoa khám). "
            f"Các trường còn thiếu thông tin là: {', '.join(missing_field_labels) if missing_field_labels else 'không có'}. "
            "Hãy phân tích câu của người dùng và trích xuất thông tin để điền vào các trường còn thiếu. "
            "Nếu người dùng không cung cấp đủ thông tin, hãy yêu cầu họ cung cấp thêm các trường còn thiếu (chỉ yêu cầu các trường trong danh sách trên). "
            "Nếu tất cả các trường đã được điền, hãy trả về thông báo xác nhận. "
            "Trả về kết quả dưới dạng JSON với các trường đã điền nhưng viết tên các trường họ tên là name, tuổi là age, số điện thoại là phone, triệu chứng là symptoms, chuyên khoa là departments, form trả về chỉ gồm các trường đã có thông tin và câu trả lời tự nhiên bằng tiếng Việt."        )

        response = openai.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "Bạn là một chatbot trợ giúp điền form đăng ký khám bệnh tại bệnh viện. Trả về kết quả dưới dạng JSON với hai phần: 'form' chứa dữ liệu điền vào form và 'reply' chứa câu trả lời tự nhiên."},
                {"role": "user", "content": prompt}
            ]
        )

        reply = response.choices[0].message.content
        
        import json
        result = json.loads(reply)  
        sanitized_form = {}
        for key, value in result.get("form", {}).items():
            sanitized_form[key] = "" if value is None else value
        final_form = {**request.formData, **sanitized_form}
        return {
            "form": final_form,
            "reply": result.get("reply", "Đã xử lý câu hỏi của bạn.")
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5001)