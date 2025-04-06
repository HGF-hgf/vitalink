from typing import List
import openai


class Reflection():
    def __init__(self, llm):
        self.llm = llm

    def _concat_and_format_texts(self, data):
        concatenated_texts = []
        for entry in data:
            role = entry.sender
            message = entry.message
            concatenated_texts.append(f"{role}: {message} \n")
        return ''.join(concatenated_texts)

    
    def __call__(self, chat_history, last_items_considered=100):
        
        if len(chat_history) >= last_items_considered:
            chat_history = chat_history[len(chat_history) - last_items_considered:]

        history_string = self._concat_and_format_texts(chat_history)

        higher_level_summaries_prompt = """Given a chat history and the latest user question which might reference context in the chat history, formulate a standalone question in Vietnamese which can be understood without the chat history. Do NOT answer the question, just reformulate it if needed and otherwise return it as is. {history_string}
        """.format(history_string=history_string)

        print(higher_level_summaries_prompt)

        completion = openai.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "user",
                    "content": higher_level_summaries_prompt
                }
            ]
        )
    
        return completion.choices[0].message.content
