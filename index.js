"use client";
import { useState, useEffect } from "react";

function useDebounce(value, delay) {
  const [debouncedValue, setDebouncedValue] = useState(value);

  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedValue(value);
    }, delay);

    return () => clearTimeout(timer);
  }, [value, delay]);

  return debouncedValue;
}

export default function FormChatbot() {
  const [formData, setFormData] = useState({
    name: "",
    cccd: "",
    dob: "",
    gender: "",
    province: "",
    district: "",
    ward: "",
    address: "",
    phone: "",
    symptoms: "",
    department: "",
  });
  const [chatHistory, setChatHistory] = useState([]);
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);
  const [socket, setSocket] = useState(null);
  const [userId, setUserId] = useState(null);

  const debouncedFormData = useDebounce(formData, 500);

  useEffect(() => {
    const ws = new WebSocket("ws://localhost:5001/api/chat");
    setSocket(ws);

    ws.onopen = () => {
      console.log("WebSocket connection established");
      ws.send(JSON.stringify({ type: "init" })); // Không cần message
    };

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.user_id) {
        setUserId(data.user_id);
        localStorage.setItem("user_id", data.user_id);
      }
      if (Array.isArray(data.chat_history)) {
        setChatHistory(data.chat_history.map((msg) => ({ sender: msg.sender, text: msg.message })));
      } else {
        if (data.reply && data.reply !== "Cập nhật form thành công.") {
          setChatHistory((prev) => [...prev, { sender: "bot", text: data.reply }]);
        }
        if (data.form) {
          setFormData((prev) => ({ ...prev, ...data.form }));
        }
      }
      setLoading(false);
    };

    ws.onclose = () => {
      console.log("WebSocket connection closed");
    };

    ws.onerror = (error) => {
      console.error("WebSocket error:", error);
    };

    return () => ws.close();
  }, []);

  useEffect(() => {
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ type: "formUpdate", data: debouncedFormData }));
    }
  }, [debouncedFormData, socket]);

  const handleChat = (msg) => {
    if (!msg.trim() || !socket || socket.readyState !== WebSocket.OPEN) return;
    setLoading(true);
    setChatHistory((prev) => [...prev, { sender: "user", text: msg }]);
    socket.send(JSON.stringify({ type: "chat", message: msg }));
    setMessage("");
  };

  const handleKeyPress = (e) => {
    if (e.key === "Enter") {
      handleChat(message);
    }
  };

  return (
    <div className="grid grid-cols-2 gap-4 p-4">
      <div className="border p-4 rounded shadow">
        <h2 className="text-xl font-bold">Đăng ký khám bệnh</h2>
        <input className="border p-2 w-full mt-2" name="name" placeholder="Họ và tên" value={formData.name} onChange={(e) => setFormData({ ...formData, name: e.target.value })} />
        <input className="border p-2 w-full mt-2" name="dob" placeholder="Ngày sinh" value={formData.dob} onChange={(e) => setFormData({ ...formData, dob: e.target.value })} />
        <input className="border p-2 w-full mt-2" name="gender" placeholder="Giới tính" value={formData.gender} onChange={(e) => setFormData({ ...formData, gender: e.target.value })} />
        <input className="border p-2 w-full mt-2" name="phone" placeholder="Số điện thoại" value={formData.phone} onChange={(e) => setFormData({ ...formData, phone: e.target.value })} />
        <input className="border p-2 w-full mt-2" name="cccd" placeholder="Số Căn cước công dân" value={formData.cccd} onChange={(e) => setFormData({ ...formData, cccd: e.target.value })} />
        <input className="border p-2 w-full mt-2" name="province" placeholder="Tỉnh/Thành" value={formData.province} onChange={(e) => setFormData({ ...formData, province: e.target.value })} />
        <input className="border p-2 w-full mt-2" name="district" placeholder="Quận/Huyện" value={formData.district} onChange={(e) => setFormData({ ...formData, district: e.target.value })} />
        <input className="border p-2 w-full mt-2" name="ward" placeholder="Xã/Phường" value={formData.ward} onChange={(e) => setFormData({ ...formData, ward: e.target.value })} />
        <input className="border p-2 w-full mt-2" name="address" placeholder="Địa chỉ" value={formData.address} onChange={(e) => setFormData({ ...formData, address: e.target.value })} />
        <input className="border p-2 w-full mt-2" name="symptoms" placeholder="Triệu chứng" value={formData.symptoms} onChange={(e) => setFormData({ ...formData, symptoms: e.target.value })} />
        <input className="border p-2 w-full mt-2" name="department" placeholder="Chuyên khoa khám" value={formData.department} onChange={(e) => setFormData({ ...formData, department: e.target.value })} />
      </div>

      <div className="border p-4 rounded shadow flex flex-col h-96">
        <h2 className="text-xl font-bold">Chatbot</h2>
        <div className="flex-1 overflow-auto">
          {chatHistory.map((msg, idx) => (
            <div key={idx} className={`p-2 ${msg.sender === "user" ? "text-right" : "text-left"}`}>
              <span className={`inline-block p-2 rounded-lg ${msg.sender === "user" ? "bg-blue-100" : "bg-gray-200"}`}>
                {msg.text}
              </span>
            </div>
          ))}
          {loading && <span className="text-gray-500">Chatbot đang suy nghĩ...</span>}
        </div>
        <div className="mt-2">
          <input
            className="border p-2 w-full"
            placeholder="Nhập tin nhắn cho chatbot..."
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            onKeyPress={handleKeyPress}
          />
        </div>
      </div>
    </div>
  );
}