from google import genai
import pandas as pd
import json
import numpy as np
from pymongo import MongoClient
from sklearn.metrics.pairwise import cosine_similarity as cosine
import time
from google.api_core import exceptions
import openai
from google.genai import types
import os
import dotenv
dotenv.load_dotenv()

db_client = MongoClient(os.getenv("MONGODB_URI"))
client = genai.Client(api_key= os.getenv("GOOGLE_API_KEY"))
openai.api_key = os.getenv("OPENAI_API_KEY")
db = db_client['Vitalink']
collection = db['test']


def get_embedding(text, retries=5):
    for attempt in range(retries):
        try:
            result = client.models.embed_content(
                model="gemini-embedding-exp-03-07",
                contents=text,
                config=types.EmbedContentConfig(task_type="SEMANTIC_SIMILARITY"))
            return result.embeddings[0].values
        except exceptions.ResourceExhausted as e:
            if attempt < retries - 1:
                print(f"Quota vượt quá, thử lại sau {2 ** attempt} giây...")
                time.sleep(2 ** attempt)  # Đợi 1s, 2s, 4s,...
            else:
                raise e
            
            
def vector_search(query, collection):
    query_embedding = get_embedding(query)

    vector_search_stage = {
        "$vectorSearch": {
            "index": "vector_index",
            "path": "embeddings",
            "queryVector": query_embedding,
            "numCandidates": 19,
            "limit":  10
      }
    }

    project_stage = {
        "$project": {
            "Test_Name": 1,
            "Symptoms": 1,
            "Contraindications": 1,
            "score": {"$meta": "vectorSearchScore"}
        }
    }

    pipeline = [vector_search_stage, project_stage]
    results = collection.aggregate(pipeline)
    return list(results)

def evaluate_tests(query, test_list):
    test_list_str = "\n".join(
        [f"- {result['Test_Name']} (Symptoms: {result['Symptoms']}; Contraindications: {result['Contraindications']})" 
         for result in test_list]
    )
    prompt = f"""
    Dựa trên triệu chứng của người dùng: "{query}", hãy đánh giá danh sách xét nghiệm dưới đây. 
    Trả về **tất cả các xét nghiệm thực sự cần thiết và phù hợp** dựa trên triệu chứng, loại bỏ những xét nghiệm không liên quan hoặc ít khả năng. 
    Sử dụng thông tin về triệu chứng liên quan (Symptoms) và chống chỉ định (Contraindications) để đưa ra quyết định. 
    Nếu cần nhiều hơn 5 xét nghiệm để đánh giá đầy đủ, hãy bao gồm tất cả. 
    Trả về danh sách ngắn gọn, mỗi dòng là tên xét nghiệm.

    Danh sách xét nghiệm:
    {test_list_str}

    Định dạng trả về:
    - Tên xét nghiệm 1
    - Tên xét nghiệm 2
    ... """
    
    response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "Bạn là một chatbot trợ giúp điền form đăng ký khám bệnh tại bệnh viện."},
                {"role": "user", "content": prompt}
            ]
        )
    return response.choices[0].message.content

def get_search_results(query):
    get_information = vector_search(query, collection)
    
    filtered_information = [result for result in get_information if result["score"] > 0.84]  # Ngưỡng score
    filtered_tests = evaluate_tests(query, filtered_information)
    return filtered_tests


