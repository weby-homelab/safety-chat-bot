import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold
from typing import List, Dict, Optional

class AIService:
    def __init__(self, api_key: str, model_name: str = "gemini-2.5-flash"):
        genai.configure(api_key=api_key)
        
        self.safety_settings = {
            HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
        }
        
        self.model = genai.GenerativeModel(
            model_name=model_name,
            safety_settings=self.safety_settings,
            generation_config={
                "temperature": 0.65,
                "max_output_tokens": 2048,
                "top_p": 0.9,
                "top_k": 40,
            }
        )

    async def generate_summary(self, messages: List[Dict[str, str]]) -> str:
        if not messages:
            return "Немає повідомлень для аналізу."
        
        prompt = (
            "Зроби коротке, чітке самарі розмови українською мовою. "
            "Виділи головні теми та ключові думки:\n\n"
        )
        for msg in messages:
            prompt += f"{msg.get('user', 'Користувач')}: {msg.get('text', '')}\n"
        
        response = await self.model.generate_content_async(prompt)
        return response.text.strip()

    async def factcheck(self, text: str) -> str:
        prompt = (
            "Проведи швидкий фактчекінг. Відповідай українською у форматі:\n"
            "Вердикт: [Правда / Фейк / Маніпуляція / Неперевірено]\n"
            "Пояснення: (1-2 речення)\n\n"
            f"Текст: {text}"
        )
        response = await self.model.generate_content_async(prompt)
        return response.text.strip()