"""
감정 분석 유틸리티 (v1.1)

Gemini API를 사용해 메시지의 감정을 분석하고
Discord 이모지 리액션 목록을 반환합니다.

설계 원칙:
- 분석 모델을 GeminiClient와 동기화: /model 변경 시 자동 반영
- 시스템 프롬프트 없이 JSON만 반환: 토큰 최소화
- 항상 asyncio.to_thread() 래핑: 이벤트 루프 blocking 방지
- 실패 시 빈 리스트 반환: 봇 응답 흐름에 영향 없음

[v1.1 변경]
- FIX: ANALYSIS_MODEL 하드코딩 제거
       → GeminiClient 인스턴스를 직접 참조하여
         /model 변경 시 감정 분석 모델도 자동으로 동기화
"""
from google import genai
from google.genai.types import GenerateContentConfig
from typing import List, TYPE_CHECKING
import json
import re

if TYPE_CHECKING:
    from utils.gemini_client import GeminiClient

# 감정 → 이모지 매핑 테이블
EMOTION_EMOJI_MAP: dict[str, str] = {
    # 긍정
    "happy":        "😊",
    "joy":          "😄",
    "excited":      "🎉",
    "love":         "❤️",
    "grateful":     "🙏",
    "proud":        "😤",
    "hopeful":      "🌟",
    "calm":         "😌",
    "amused":       "😂",
    # 부정
    "sad":          "😢",
    "angry":        "😡",
    "frustrated":   "😤",
    "anxious":      "😰",
    "scared":       "😱",
    "disappointed": "😞",
    "bored":        "😒",
    "confused":     "🤔",
    "disgusted":    "🤢",
    # 중립/기타
    "surprised":    "😮",
    "neutral":      "😐",
    "curious":      "🧐",
    "tired":        "😴",
    "sarcastic":    "🙃",
    "nostalgic":    "🥺",
    "determined":   "💪",
}

ANALYSIS_PROMPT = """Analyze the emotion of the following message and respond ONLY with a JSON object.
No explanation, no markdown, no extra text. Just the JSON.

Rules:
- emotions: list of 1~3 emotion labels from this set only:
  [happy, joy, excited, love, grateful, proud, hopeful, calm, amused,
   sad, angry, frustrated, anxious, scared, disappointed, bored, confused, disgusted,
   surprised, neutral, curious, tired, sarcastic, nostalgic, determined]
- confidence: float 0.0~1.0
- If the message is too short (<3 chars) or meaningless, return: {"emotions": ["neutral"], "confidence": 0.3}

Response format:
{"emotions": ["<emotion1>", "<emotion2>"], "confidence": 0.85}

Message to analyze:
"""


class EmotionAnalyzer:
    """
    Gemini 기반 감정 분석기

    GeminiClient를 참조하여 현재 선택된 모델을 동적으로 사용합니다.
    /model 변경 시 감정 분석 모델도 자동으로 동기화됩니다.
    """

    MIN_CONFIDENCE = 0.5
    MIN_TEXT_LEN   = 2

    def __init__(self, api_key: str, gemini_client: "GeminiClient"):
        self.client         = genai.Client(api_key=api_key)
        self.gemini_client  = gemini_client   # model_name 동기화용
        self._config        = GenerateContentConfig(
            temperature=0.1,
            top_p=0.9,
            max_output_tokens=64,
        )

    @property
    def current_model(self) -> str:
        """현재 GeminiClient의 모델명을 실시간으로 반환"""
        return self.gemini_client.model_name

    def analyze(self, text: str) -> List[str]:
        """
        텍스트 감정 분석 (동기) → Discord 이모지 리스트 반환
        asyncio.to_thread()로 감싸서 호출할 것.
        """
        text = text.strip()

        if len(text) < self.MIN_TEXT_LEN:
            return []

        if len(text) > 200:
            text = text[:200] + "..."

        try:
            response = self.client.models.generate_content(
                model=self.current_model,   # 항상 최신 모델 사용
                contents=ANALYSIS_PROMPT + text,
                config=self._config,
            )
            raw = response.text.strip()
            raw = re.sub(r"```json|```", "", raw).strip()

            data       = json.loads(raw)
            emotions   = data.get("emotions", [])
            confidence = float(data.get("confidence", 0.0))

            if confidence < self.MIN_CONFIDENCE:
                return []

            emojis = [
                EMOTION_EMOJI_MAP[e]
                for e in emotions
                if e in EMOTION_EMOJI_MAP
            ]
            print(f"🎭 감정 분석 [{self.current_model}]: {emotions} ({confidence:.2f}) → {emojis}")
            return emojis

        except Exception as e:
            print(f"⚠️ 감정 분석 실패 (무시됨): {e}")
            return []