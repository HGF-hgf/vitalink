from google import genai


text = "Người bệnh có tiền sử dị ứng với thuốc kháng sinh nhóm beta-lactam và cephalosporin. Bệnh nhân có tiền sử bệnh gan nặng. Bệnh nhân đang mang thai hoặc cho con bú. Bệnh nhân có tiền sử bệnh thận nặng. Bệnh nhân đang dùng thuốc chống đông máu hoặc thuốc điều trị tiểu đường."
result  = client.models.embed_content(
                model="gemini-embedding-exp-03-07",
                contents=text)
print(result.embeddings)