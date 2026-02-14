"""
채팅 메시지 감지 및 응답 처리 Cog (v3.4 - 최적화)
"""
import discord
from discord.ext import commands
import asyncio
import random
from typing import List, Dict, Optional

from config.settings import CHANNEL_BOT, MESSAGE_COLLECT_DELAY, MAX_HISTORY_LENGTH
from config.settings import SPLIT_PARTS, SPLIT_MIN_DELAY, SPLIT_MAX_DELAY
from utils.gemini_client import GeminiClient
from utils.message_splitter import MessageSplitter


class ChatHandler(commands.Cog):
    """채팅 메시지를 감지하고 응답하는 Cog (자동 이미지/스티커 분석)"""
    
    def __init__(self, bot: commands.Bot, gemini_client: GeminiClient):
        self.bot = bot
        self.gemini_client = gemini_client
        self.user_histories: Dict[int, List[Dict]] = {}
        self.pending_messages: List[Dict] = []
        self.split_mode = False
        self.collecting = False
    
    def get_user_history(self, user_id: int) -> List[Dict]:
        """사용자의 대화 히스토리 가져오기"""
        if user_id not in self.user_histories:
            self.user_histories[user_id] = []
        return self.user_histories[user_id]
    
    def add_to_user_history(self, user_id: int, role: str, content: str):
        """사용자의 대화 히스토리에 추가"""
        history = self.get_user_history(user_id)
        history.append({"role": role, "parts": [{"text": content}]})
        
        if len(history) > MAX_HISTORY_LENGTH:
            self.user_histories[user_id] = history[-MAX_HISTORY_LENGTH:]
    
    def clear_user_history(self, user_id: int):
        """특정 사용자의 히스토리 초기화"""
        if user_id in self.user_histories:
            self.user_histories[user_id] = []
            print(f"🗑️ {user_id} 사용자의 대화 히스토리가 초기화되었습니다.")
    
    async def extract_images_from_message(self, message: discord.Message) -> List[Dict]:
        """메시지에서 이미지/스티커 추출"""
        images = []
        
        for attachment in message.attachments:
            if attachment.content_type and attachment.content_type.startswith('image/'):
                try:
                    image_data = await attachment.read()
                    images.append({
                        "data": image_data,
                        "mime_type": attachment.content_type,
                        "filename": attachment.filename,
                        "type": "attachment"
                    })
                    print(f"📷 이미지 감지: {attachment.filename} ({attachment.content_type})")
                except Exception as e:
                    print(f"❌ 이미지 다운로드 실패: {e}")
        
        if message.stickers:
            for sticker in message.stickers:
                try:
                    import aiohttp
                    async with aiohttp.ClientSession() as session:
                        async with session.get(sticker.url) as response:
                            if response.status == 200:
                                sticker_data = await response.read()
                                content_type = response.headers.get('Content-Type', 'image/png')
                                images.append({
                                    "data": sticker_data,
                                    "mime_type": content_type,
                                    "filename": f"{sticker.name}.png",
                                    "type": "sticker"
                                })
                                print(f"🎭 스티커 감지: {sticker.name}")
                except Exception as e:
                    print(f"❌ 스티커 다운로드 실패: {e}")
        
        return images
    
    def has_media(self, message: discord.Message) -> bool:
        """메시지에 미디어(이미지/스티커)가 있는지 확인"""
        has_image = any(
            att.content_type and att.content_type.startswith('image/')
            for att in message.attachments
        )
        return has_image or len(message.stickers) > 0
    
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """메시지 수신 이벤트 핸들러"""
        if message.author == self.bot.user:
            return
        if message.channel.id != CHANNEL_BOT:
            return
        if message.content.startswith('\\'):
            return
        if message.content.startswith('/'):
            return
        
        if self.has_media(message):
            print(f"🖼️ 미디어 감지됨 - 즉시 분석 시작")
            await self.process_message_with_media(message)
            return
        
        self.pending_messages.append({
            'content': message.content,
            'author': message.author.name,
            'user_id': message.author.id,
            'timestamp': message.created_at
        })
        
        if self.collecting:
            return
        
        self.collecting = True
        await asyncio.sleep(MESSAGE_COLLECT_DELAY)
        self.collecting = False
        
        await self.generate_and_send_response(message.channel, message.author.id)
    
    async def process_message_with_media(self, message: discord.Message):
        """미디어가 포함된 메시지 즉시 처리"""
        user_id = message.author.id
        
        async with message.channel.typing():
            images = await self.extract_images_from_message(message)
            if not images:
                return
            
            first_image = images[0]
            user_text = message.content.strip()
            
            if user_text:
                prompt = user_text
            else:
                if first_image['type'] == 'sticker':
                    prompt = "이 스티커에 대해 설명해주고, 어떤 감정이나 상황을 표현하는지 알려줘."
                else:
                    prompt = "이 이미지에 대해 자세히 설명해주세요. 무엇이 보이나요?"
            
            user_history = self.get_user_history(user_id)
            
            if first_image['type'] == 'sticker':
                context_text = f"{user_text}\n[스티커: {first_image['filename']}]" if user_text else f"[스티커: {first_image['filename']}]"
            else:
                context_text = f"{user_text}\n[이미지: {first_image['filename']}]" if user_text else f"[이미지: {first_image['filename']}]"
            
            self.add_to_user_history(user_id, "user", context_text)
            
            try:
                response_text = self.gemini_client.generate_response_with_image(
                    text=prompt,
                    image_data=first_image['data'],
                    mime_type=first_image['mime_type'],
                    history=user_history[:-1]
                )
                self.add_to_user_history(user_id, "model", response_text)
                
                if self.split_mode:
                    await self.send_split_message(message.channel, response_text)
                else:
                    await message.channel.send(response_text.replace('\\n', '\n'))
                
                print(f"🖼️ {first_image['type']} 분석 완료: {first_image['filename']} (user: {user_id})")
                
            except Exception as e:
                print(f"❌ 이미지 분석 중 오류: {e}")
                await message.channel.send("앗, 이미지를 분석하는 중에 문제가 생겼네... 😅")
    
    async def generate_and_send_response(self, channel: discord.TextChannel, user_id: int):
        """수집된 텍스트 메시지 응답 생성"""
        if not self.pending_messages:
            return
        
        context = "\n".join([
            f"{msg['author']}: {msg['content']}"
            for msg in self.pending_messages
        ])
        self.pending_messages.clear()
        
        user_history = self.get_user_history(user_id)
        self.add_to_user_history(user_id, "user", context)
        
        try:
            response_text = self.gemini_client.generate_response(context, user_history[:-1])
            self.add_to_user_history(user_id, "model", response_text)
            
            if self.split_mode:
                await self.send_split_message(channel, response_text)
            else:
                await channel.send(response_text.replace('\\n', '\n'))
            
            print(f"💬 {user_id} 사용자와 대화 (히스토리: {len(user_history)}개)")
            
        except Exception as e:
            print(f"❌ 응답 생성 중 오류: {e}")
            await channel.send("앗, 뭔가 잘못됐네... 😅")
    
    async def send_split_message(self, channel: discord.TextChannel, text: str):
        """메시지 분할 전송"""
        chunks = MessageSplitter.smart_split(text, SPLIT_PARTS)
        for i, chunk in enumerate(chunks):
            if chunk:
                await channel.send(chunk)
                if i < len(chunks) - 1:
                    await asyncio.sleep(random.uniform(SPLIT_MIN_DELAY, SPLIT_MAX_DELAY))
    
    def set_split_mode(self, enabled: bool):
        """Split 모드 설정"""
        self.split_mode = enabled
    
    def get_conversation_history(self, user_id: int = None) -> List[Dict]:
        """대화 히스토리 반환"""
        if user_id is None:
            total = sum(len(h) for h in self.user_histories.values())
            return [{"total_users": len(self.user_histories), "total_messages": total}]
        return self.get_user_history(user_id)
    
    def clear_history(self, user_id: int = None):
        """대화 히스토리 초기화"""
        if user_id is None:
            self.user_histories.clear()
            print("🗑️ 모든 사용자의 대화 히스토리가 초기화되었습니다.")
        else:
            self.clear_user_history(user_id)
    
    def get_user_stats(self) -> Dict:
        """사용자별 통계 반환"""
        return {
            "total_users": len(self.user_histories),
            "users": [
                {"user_id": uid, "message_count": len(hist)}
                for uid, hist in self.user_histories.items()
            ]
        }


async def setup(bot: commands.Bot):
    """Cog 설정 함수 (동적 로드용)"""
    if not hasattr(bot, 'gemini_client'):
        raise RuntimeError(
            "ChatHandler를 로드하기 전에 bot.gemini_client를 설정해야 합니다."
        )
    await bot.add_cog(ChatHandler(bot, bot.gemini_client))
    print("✅ ChatHandler Cog 동적 로드 완료")