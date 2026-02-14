"""
Gemini API 클라이언트 관리 유틸리티 (v4.1 - 최적화: 미사용 import 제거)
"""
from google import genai
from google.genai.types import GenerateContentConfig
from typing import List, Dict, Optional
import base64


class GeminiClient:
    """Gemini API와의 상호작용을 관리하는 클래스 (Vision 포함)"""
    
    def __init__(self, api_key: str, model_name: str, temperature: float, top_p: float, max_output_tokens: int):
        self.client = genai.Client(api_key=api_key)
        self.model_name = model_name
        self.temperature = temperature
        self.top_p = top_p
        self.max_output_tokens = max_output_tokens
        self.system_prompt = ""
        self.base_prompt = ""
        self.memory_text = ""
        self.current_prompt_file = ""
    
    def load_system_prompt(self, prompt_file: str) -> bool:
        """시스템 프롬프트 파일 로드"""
        try:
            with open(prompt_file, 'r', encoding='utf-8') as f:
                self.base_prompt = f.read()
            self.system_prompt = self.base_prompt
            self.current_prompt_file = prompt_file
            print(f"✅ 프롬프트 파일 로드 완료: {prompt_file}")
            return True
        except FileNotFoundError:
            print(f"⚠️ {prompt_file} 파일을 찾을 수 없습니다.")
            self.base_prompt = "당신은 '땅콩'이라는 사람의 성격을 가진 친근한 챗봇입니다."
            self.system_prompt = self.base_prompt
            self.current_prompt_file = "default"
            return False
    
    def create_config(self) -> GenerateContentConfig:
        """현재 설정으로 GenerateContentConfig 생성"""
        return GenerateContentConfig(
            temperature=self.temperature,
            top_p=self.top_p,
            max_output_tokens=self.max_output_tokens,
            system_instruction=self.system_prompt
        )
    
    def update_settings(self, model_name: str = None, temperature: float = None, top_p: float = None):
        """모델 설정 업데이트"""
        if model_name:
            self.model_name = model_name
        if temperature is not None:
            self.temperature = temperature
        if top_p is not None:
            self.top_p = top_p
    
    def update_memories(self, memory_text: str):
        """메모리 텍스트 업데이트 및 시스템 프롬프트 갱신"""
        self.memory_text = memory_text
        self.system_prompt = f"{self.base_prompt}\n\n{self.memory_text}" if self.memory_text else self.base_prompt
        print(f"🧠 메모리 업데이트 완료 - 프롬프트 길이: {len(self.system_prompt)} 문자")
    
    def _convert_history_format(self, history: List[Dict]) -> List[Dict]:
        """history 형식 변환"""
        if not history:
            return []
        
        converted = []
        for msg in history:
            role = "model" if msg["role"] == "model" else msg["role"]
            text_content = ""
            if "parts" in msg:
                for part in msg["parts"]:
                    if isinstance(part, dict) and "text" in part:
                        text_content += part["text"]
            converted.append({"role": role, "parts": [{"text": text_content}]})
        
        return converted
    
    def generate_response(self, context: str, history: List[Dict] = None) -> str:
        """대화 컨텍스트를 기반으로 응답 생성 (텍스트만)"""
        try:
            config = self.create_config()
            converted_history = self._convert_history_format(history) if history else []
            messages = converted_history + [{"role": "user", "parts": [{"text": context}]}]
            
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=messages,
                config=config
            )
            return response.text
        except Exception as e:
            raise Exception(f"응답 생성 실패: {e}")
    
    def generate_response_with_image(self, text: str, image_data: bytes, mime_type: str = "image/png", history: List[Dict] = None) -> str:
        """이미지와 텍스트를 함께 분석하여 응답 생성"""
        try:
            config = self.create_config()
            converted_history = self._convert_history_format(history) if history else []
            
            image_part = {"inline_data": {"mime_type": mime_type, "data": base64.b64encode(image_data).decode('utf-8')}}
            current_message = {"role": "user", "parts": [{"text": text}, image_part]}
            messages = converted_history + [current_message]
            
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=messages,
                config=config
            )
            return response.text
        except Exception as e:
            raise Exception(f"이미지 분석 실패: {e}")
    
    def analyze_image(self, image_data: bytes, mime_type: str = "image/png", prompt: str = None) -> str:
        """이미지 단독 분석"""
        if prompt is None:
            prompt = "이 이미지에 대해 자세히 설명해주세요. 무엇이 보이나요?"
        return self.generate_response_with_image(prompt, image_data, mime_type)
    
    async def download_and_encode_image(self, url: str) -> tuple:
        """URL에서 이미지 다운로드 및 인코딩"""
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    return await response.read(), response.headers.get('Content-Type', 'image/png')
                else:
                    raise Exception(f"이미지 다운로드 실패: HTTP {response.status}")