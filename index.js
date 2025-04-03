// "use client";
// import { useState } from "react";

// export default function FormChatbot() {
//   const [formData, setFormData] = useState({ name: "", phone: "", age: "", symptoms: "", department: "" });
//   const [chatHistory, setChatHistory] = useState([]);
//   const [message, setMessage] = useState(""); // State cho ô input chat
//   const [loading, setLoading] = useState(false);

//   // Xử lý thay đổi trong form
//   const handleInputChange = (e) => {
//     const { name, value } = e.target;
//     setFormData({ ...formData, [name]: value });
//   };

//   // Gửi tin nhắn đến backend và nhận phản hồi
//   const handleChat = async (msg) => {
//     if (!msg.trim()) return; // Không gửi nếu tin nhắn rỗng
//     setLoading(true);
//     setChatHistory([...chatHistory, { sender: "user", text: msg }]);

//     try {
//       const response = await fetch("http://localhost:5001/api/chat", {
//         method: "POST",
//         headers: { "Content-Type": "application/json" },
//         body: JSON.stringify({ message: msg, formData }),
//       });
//       const data = await response.json();

//       // Cập nhật formData với dữ liệu từ backend
//       setFormData((prev) => ({ ...prev, ...data.form }));

//       // Thêm phản hồi của chatbot vào lịch sử chat
//       setChatHistory((prev) => [...prev, { sender: "bot", text: data.reply }]);
//     } catch (error) {
//       console.error("Lỗi khi gửi tin nhắn:", error);
//       setChatHistory((prev) => [...prev, { sender: "bot", text: "Có lỗi xảy ra, vui lòng thử lại!" }]);
//     } finally {
//       setLoading(false);
//     }
//   };

//   // Xử lý khi người dùng nhấn Enter trong ô chat
//   const handleKeyPress = (e) => {
//     if (e.key === "Enter") {
//       handleChat(message);
//       setMessage(""); // Xóa ô input sau khi gửi
//     }
//   };

//   return (
//     <div className="grid grid-cols-2 gap-4 p-4">
//       {/* Form Section */}
//       <div className="border p-4 rounded shadow">
//         <h2 className="text-xl font-bold">Đăng ký khám bệnh</h2>
//         <input
//           className="border p-2 w-full mt-2"
//           name="name"
//           placeholder="Họ và tên"
//           value={formData.name}
//           onChange={handleInputChange}
//         />
//         <input
//           className="border p-2 w-full mt-2"
//           name="phone"
//           placeholder="Số điện thoại"
//           value={formData.phone}
//           onChange={handleInputChange}
//         />
//         <input
//           className="border p-2 w-full mt-2"
//           name="age"
//           placeholder="Tuổi"
//           value={formData.age}
//           onChange={handleInputChange}
//         />
//         <input
//           className="border p-2 w-full mt-2"
//           name="symptoms"
//           placeholder="Triệu chứng"
//           value={formData.symptoms}
//           onChange={handleInputChange}
//         />
//         <input
//           className="border p-2 w-full mt-2"
//           name="department"
//           placeholder="Chuyên khoa khám"
//           value={formData.department}
//           onChange={handleInputChange}
//         />

//       </div>

//       {/* Chatbot Section */}
//       <div className="border p-4 rounded shadow flex flex-col h-96">
//         <h2 className="text-xl font-bold">Chatbot</h2>
//         <div className="flex-1 overflow-auto">
//           {chatHistory.map((msg, idx) => (
//             <div
//               key={idx}
//               className={`p-2 ${msg.sender === "user" ? "text-right" : "text-left"}`}
//             >
//               <span
//                 className={`inline-block p-2 rounded-lg ${
//                   msg.sender === "user" ? "bg-blue-100" : "bg-gray-200"
//                 }`}
//               >
//                 {msg.text}
//               </span>
//             </div>
//           ))}
//           {loading && <span className="text-gray-500">Chatbot đang suy nghĩ...</span>}
//         </div>
//         {/* Ô nhập tin nhắn */}
//         <div className="mt-2">
//           <input
//             className="border p-2 w-full"
//             placeholder="Nhập tin nhắn cho chatbot..."
//             value={message}
//             onChange={(e) => setMessage(e.target.value)}
//             onKeyPress={handleKeyPress}
//           />
//         </div>
//       </div>
//     </div>
//   );
// }

// "use client";
// import { useState } from "react";

// export default function FormChatbot() {
//   const [formData, setFormData] = useState({ name: "", phone: "", age: "", symptoms: "", department: "" });
//   const [chatHistory, setChatHistory] = useState([]);
//   const [message, setMessage] = useState(""); // State cho ô input chat
//   const [loading, setLoading] = useState(false);

//   // Xử lý thay đổi trong form
//   const handleInputChange = (e) => {
//     const { name, value } = e.target;
//     setFormData({ ...formData, [name]: value });
//   };

//   // Gửi tin nhắn đến backend và nhận phản hồi
//   const handleChat = async (msg) => {
//     if (!msg.trim()) return; // Không gửi nếu tin nhắn rỗng
//     setLoading(true);
//     setChatHistory([...chatHistory, { sender: "user", text: msg }]);

//     try {
//       const response = await fetch("http://localhost:5001/api/chat", {
//         method: "POST",
//         headers: { "Content-Type": "application/json" },
//         body: JSON.stringify({ message: msg, formData }),
//       });
//       const data = await response.json();

//       // Cập nhật formData với dữ liệu từ backend
//       setFormData((prev) => ({ ...prev, ...data.form }));

//       // Thêm phản hồi của chatbot vào lịch sử chat
//       setChatHistory((prev) => [...prev, { sender: "bot", text: data.reply }]);
//     } catch (error) {
//       console.error("Lỗi khi gửi tin nhắn:", error);
//       setChatHistory((prev) => [...prev, { sender: "bot", text: "Có lỗi xảy ra, vui lòng thử lại!" }]);
//     } finally {
//       setLoading(false);
//     }
//   };

//   // Xử lý khi người dùng nhấn Enter trong ô chat
//   const handleKeyPress = (e) => {
//     if (e.key === "Enter") {
//       handleChat(message);
//       setMessage(""); // Xóa ô input sau khi gửi
//     }
//   };

//   return (
//     <div className="grid grid-cols-2 gap-4 p-4">
//       {/* Form Section */}
//       <div className="border p-4 rounded shadow">
//         <h2 className="text-xl font-bold">Đăng ký khám bệnh</h2>
//         <input
//           className="border p-2 w-full mt-2"
//           name="name"
//           placeholder="Họ và tên"
//           value={formData.name}
//           onChange={handleInputChange}
//         />
//         <input
//           className="border p-2 w-full mt-2"
//           name="phone"
//           placeholder="Số điện thoại"
//           value={formData.phone}
//           onChange={handleInputChange}
//         />
//         <input
//           className="border p-2 w-full mt-2"
//           name="age"
//           placeholder="Tuổi"
//           value={formData.age}
//           onChange={handleInputChange}
//         />
//         <input
//           className="border p-2 w-full mt-2"
//           name="symptoms"
//           placeholder="Triệu chứng"
//           value={formData.symptoms}
//           onChange={handleInputChange}
//         />
//         <input
//           className="border p-2 w-full mt-2"
//           name="department"
//           placeholder="Chuyên khoa khám"
//           value={formData.department}
//           onChange={handleInputChange}
//         />

//       </div>

//       {/* Chatbot Section */}
//       <div className="border p-4 rounded shadow flex flex-col h-96">
//         <h2 className="text-xl font-bold">Chatbot</h2>
//         <div className="flex-1 overflow-auto">
//           {chatHistory.map((msg, idx) => (
//             <div
//               key={idx}
//               className={`p-2 ${msg.sender === "user" ? "text-right" : "text-left"}`}
//             >
//               <span
//                 className={`inline-block p-2 rounded-lg ${
//                   msg.sender === "user" ? "bg-blue-100" : "bg-gray-200"
//                 }`}
//               >
//                 {msg.text}
//               </span>
//             </div>
//           ))}
//           {loading && <span className="text-gray-500">Chatbot đang suy nghĩ...</span>}
//         </div>
//         {/* Ô nhập tin nhắn */}
//         <div className="mt-2">
//           <input
//             className="border p-2 w-full"
//             placeholder="Nhập tin nhắn cho chatbot..."
//             value={message}
//             onChange={(e) => setMessage(e.target.value)}
//             onKeyPress={handleKeyPress}
//           />
//         </div>
//       </div>
//     </div>
//   );
// }

"use client";
import { useState, useEffect } from "react";
import axios from "axios";

// Hook debounce tùy chỉnh
function useDebounce(value, delay) {
  const [debouncedValue, setDebouncedValue] = useState(value);

  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedValue(value);
    }, delay);

    return () => {
      clearTimeout(timer); // Xóa timer nếu giá trị thay đổi trước khi hết delay
    };
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

  // Debounce formData với delay 500ms
  const debouncedFormData = useDebounce(formData, 500);

  // Khởi tạo WebSocket
  useEffect(() => {
    const ws = new WebSocket("ws://localhost:5001/api/chat");
    setSocket(ws);

    ws.onopen = () => {
      console.log("WebSocket connection established");
    };

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (Array.isArray(data)) {
        setChatHistory(data.map((msg) => ({ sender: msg.sender, text: msg.message })));
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

    return () => {
      ws.close();
    };
  }, []);

  // Gửi formData qua WebSocket khi debouncedFormData thay đổi
  useEffect(() => {
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ type: "formUpdate", data: debouncedFormData }));
    }
  }, [debouncedFormData, socket]);

  // Gửi tin nhắn chat
  const handleChat = (msg) => {
    if (!msg.trim() || !socket || socket.readyState !== WebSocket.OPEN) return;
    setLoading(true);
    setChatHistory([...chatHistory, { sender: "user", text: msg }]);
    socket.send(JSON.stringify({ type: "chat", message: msg }));
    setMessage("");
    // setLoading(false);
  };

  const handleKeyPress = (e) => {
    if (e.key === "Enter") {
      handleChat(message);
    }
  };

  return (
    <div className="grid grid-cols-2 gap-4 p-4">
      {/* Form Section */}
      <div className="border p-4 rounded shadow">
        <h2 className="text-xl font-bold">Đăng ký khám bệnh</h2>
        <input
          className="border p-2 w-full mt-2"
          name="name"
          placeholder="Họ và tên"
          value={formData.name}
          onChange={(e) => setFormData({ ...formData, name: e.target.value })}
        />
        <input
          className="border p-2 w-full mt-2"
          name="dob"
          placeholder="Ngày sinh"
          value={formData.dob}
          onChange={(e) => setFormData({ ...formData, dob: e.target.value })}
        />
        <input
          className="border p-2 w-full mt-2"
          name="gender"
          placeholder="Giới tính"
          value={formData.gender}
          onChange={(e) => setFormData({ ...formData, gender: e.target.value })}
        />
        <input
          className="border p-2 w-full mt-2"
          name="phone"
          placeholder="Số điện thoại"
          value={formData.phone}
          onChange={(e) => setFormData({ ...formData, phone: e.target.value })}
        />
        <input
          className="border p-2 w-full mt-2"
          name="cccd"
          placeholder="Số Căn cước công dân"
          value={formData.cccd}
          onChange={(e) => setFormData({ ...formData, cccd: e.target.value })} // Sửa lỗi: dùng cccd thay vì phone
        />
        <input
          className="border p-2 w-full mt-2"
          name="province"
          placeholder="Tỉnh/Thành"
          value={formData.province}
          onChange={(e) => setFormData({ ...formData, province: e.target.value })}
        />
        <input
          className="border p-2 w-full mt-2"
          name="district"
          placeholder="Quận/Huyện"
          value={formData.district}
          onChange={(e) => setFormData({ ...formData, district: e.target.value })}
        />
        <input
          className="border p-2 w-full mt-2"
          name="ward"
          placeholder="Xã/Phường"
          value={formData.ward}
          onChange={(e) => setFormData({ ...formData, ward: e.target.value })}
        />
        <input
          className="border p-2 w-full mt-2"
          name="address"
          placeholder="Địa chỉ"
          value={formData.address}
          onChange={(e) => setFormData({ ...formData, address: e.target.value })}
        />
        <input
          className="border p-2 w-full mt-2"
          name="symptoms"
          placeholder="Triệu chứng"
          value={formData.symptoms}
          onChange={(e) => setFormData({ ...formData, symptoms: e.target.value })}
        />
        <input
          className="border p-2 w-full mt-2"
          name="department"
          placeholder="Chuyên khoa khám"
          value={formData.department}
          onChange={(e) => setFormData({ ...formData, department: e.target.value })}
        />
      </div>

      {/* Chatbot Section */}
      <div className="border p-4 rounded shadow flex flex-col h-96">
        <h2 className="text-xl font-bold">Chatbot</h2>
        <div className="flex-1 overflow-auto">
          {chatHistory.map((msg, idx) => (
            <div
              key={idx}
              className={`p-2 ${msg.sender === "user" ? "text-right" : "text-left"}`}
            >
              <span
                className={`inline-block p-2 rounded-lg ${
                  msg.sender === "user" ? "bg-blue-100" : "bg-gray-200"
                }`}
              >
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