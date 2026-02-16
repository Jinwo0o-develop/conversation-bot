"""
채팅 메시지 감지 및 응답 처리 Cog (v3.5 - 버그수정)

[수정 내역]
- BUG FIX: pending_messages / collecting 이 Cog 전역 공유 → 채널별 독립 Dict로 분리
  (멀티유저 환경에서 A의 메시지가 B의 응답에 섞이던 경쟁조건 해소)
- BUG FIX: generate_response / generate_response_with_image 가 동기 함수여서
  Discord 이벤트 루프를 blocking 하던 문제 → asyncio.to_thread() 로 래핑
- REFACTOR: generate_and_send_response 에서 마지막 발화자의 user_id 를
  정확히 추적하도록 변경
"""
import discord
from discord.ext import commands
import asyncio
import random
from typing import List, Dict

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
        self.split_mode = False

        # BUG FIX: 전역 pending_messages/collecting → 채널별 독립 상태 Dict
        # key: channel_id  |  value: {'messages': [], 'collecting': bool, 'last_user_id': int}
        self._channel_state: Dict[int, Dict] = {}

    # ------------------------------------------------------------------ #
    #  채널 상태 헬퍼
    # ------------------------------------------------------------------ #
    def _get_channel_state(self, channel_id: int) -> Dict:
        if channel_id not in self._channel_state:
            self._channel_state[channel_id] = {
                'messages': [],
                'collecting': False,
                'last_user_id': None,
            }
        return self._channel_state[channel_id]

    # ------------------------------------------------------------------ #
    #  유저 히스토리 헬퍼
    # ------------------------------------------------------------------ #
    def get_user_history(self, user_id: int) -> List[Dict]:
        if user_id not in self.user_histories:
            self.user_histories[user_id] = []
        return self.user_histories[user_id]

    def add_to_user_history(self, user_id: int, role: str, content: str):
        history = self.get_user_history(user_id)
        history.append({"role": role, "parts": [{"text": content}]})
        if len(history) > MAX_HISTORY_LENGTH:
            self.user_histories[user_id] = history[-MAX_HISTORY_LENGTH:]

    def clear_user_history(self, user_id: int):
        if user_id in self.user_histories:
            self.user_histories[user_id] = []
            print(f"🗑️ {user_id} 사용자의 대화 히스토리가 초기화되었습니다.")

    # ------------------------------------------------------------------ #
    #  이미지/스티커 추출
    # ------------------------------------------------------------------ #
    async def extract_images_from_message(self, message: discord.Message) -> List[Dict]:
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
        has_image = any(
            att.content_type and att.content_type.startswith('image/')
            for att in message.attachments
        )
        return has_image or len(message.stickers) > 0

    # ------------------------------------------------------------------ #
    #  on_message
    # ------------------------------------------------------------------ #
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author == self.bot.user:
            return
        if message.channel.id != CHANNEL_BOT:
            return
        # 백슬래시(\)로 시작하면 봇이 무시 (사용자가 조용히 대화할 때)
        if message.content.startswith('\\'):
            return
        # /로 시작하면 Discord 슬래시커맨드 → AI 응답 제외
        if message.content.startswith('/'):
            return
        # !prefix 커맨드 → process_commands 위임 후 AI 응답 제외
        if message.content.startswith('!'):
            await self.bot.process_commands(message)
            return

        if self.has_media(message):
            print("🖼️ 미디어 감지됨 - 즉시 분석 시작")
            await self.process_message_with_media(message)
            return

        # BUG FIX: 채널별 상태 사용
        state = self._get_channel_state(message.channel.id)
        state['messages'].append({
            'content': message.content,
            'author': message.author.name,
            'user_id': message.author.id,
            'timestamp': message.created_at,
        })
        state['last_user_id'] = message.author.id

        if state['collecting']:
            return

        state['collecting'] = True
        await asyncio.sleep(MESSAGE_COLLECT_DELAY)
        state['collecting'] = False

        await self.generate_and_send_response(message.channel, state['last_user_id'])

    # ------------------------------------------------------------------ #
    #  미디어 메시지 처리
    # ------------------------------------------------------------------ #
    async def process_message_with_media(self, message: discord.Message):
        user_id = message.author.id

        async with message.channel.typing():
            images = await self.extract_images_from_message(message)
            if not images:
                return

            first_image = images[0]
            user_text = message.content.strip()

            if user_text:
                prompt = user_text
            elif first_image['type'] == 'sticker':
                prompt = "이 스티커에 대해 설명해주고, 어떤 감정이나 상황을 표현하는지 알려줘."
            else:
                prompt = "이 이미지에 대해 자세히 설명해주세요. 무엇이 보이나요?"

            user_history = self.get_user_history(user_id)

            if first_image['type'] == 'sticker':
                context_text = (
                    f"{user_text}\n[스티커: {first_image['filename']}]"
                    if user_text else f"[스티커: {first_image['filename']}]"
                )
            else:
                context_text = (
                    f"{user_text}\n[이미지: {first_image['filename']}]"
                    if user_text else f"[이미지: {first_image['filename']}]"
                )

            self.add_to_user_history(user_id, "user", context_text)

            try:
                # BUG FIX: blocking 동기 API → asyncio.to_thread() 비동기 래핑
                response_text = await asyncio.to_thread(
                    self.gemini_client.generate_response_with_image,
                    prompt,
                    first_image['data'],
                    first_image['mime_type'],
                    user_history[:-1]
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

    # ------------------------------------------------------------------ #
    #  텍스트 응답 생성
    # ------------------------------------------------------------------ #
    async def generate_and_send_response(self, channel: discord.TextChannel, user_id: int):
        state = self._get_channel_state(channel.id)

        if not state['messages']:
            return

        context = "\n".join(
            f"{msg['author']}: {msg['content']}"
            for msg in state['messages']
        )
        state['messages'].clear()

        user_history = self.get_user_history(user_id)
        self.add_to_user_history(user_id, "user", context)

        try:
            async with channel.typing():
                # BUG FIX: blocking 동기 API → asyncio.to_thread() 비동기 래핑
                response_text = await asyncio.to_thread(
                    self.gemini_client.generate_response,
                    context,
                    user_history[:-1]
                )
            self.add_to_user_history(user_id, "model", response_text)

            if self.split_mode:
                await self.send_split_message(channel, response_text)
            else:
                await channel.send(response_text.replace('\\n', '\n'))

            print(f"💬 {user_id} 사용자와 대화 (히스토리: {len(self.get_user_history(user_id))}개)")

        except Exception as e:
            print(f"❌ 응답 생성 중 오류: {e}")
            await channel.send("앗, 뭔가 잘못됐네... 😅")

    # ------------------------------------------------------------------ #
    #  분할 전송
    # ------------------------------------------------------------------ #
    async def send_split_message(self, channel: discord.TextChannel, text: str):
        chunks = MessageSplitter.smart_split(text, SPLIT_PARTS)
        for i, chunk in enumerate(chunks):
            if chunk:
                await channel.send(chunk)
                if i < len(chunks) - 1:
                    await asyncio.sleep(random.uniform(SPLIT_MIN_DELAY, SPLIT_MAX_DELAY))

    # ------------------------------------------------------------------ #
    #  공개 인터페이스
    # ------------------------------------------------------------------ #
    def set_split_mode(self, enabled: bool):
        self.split_mode = enabled

    def get_conversation_history(self, user_id: int = None) -> List[Dict]:
        if user_id is None:
            total = sum(len(h) for h in self.user_histories.values())
            return [{"total_users": len(self.user_histories), "total_messages": total}]
        return self.get_user_history(user_id)

    def clear_history(self, user_id: int = None):
        if user_id is None:
            self.user_histories.clear()
            print("🗑️ 모든 사용자의 대화 히스토리가 초기화되었습니다.")
        else:
            self.clear_user_history(user_id)

    def get_user_stats(self) -> Dict:
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
        raise RuntimeError("ChatHandler를 로드하기 전에 bot.gemini_client를 설정해야 합니다.")
    await bot.add_cog(ChatHandler(bot, bot.gemini_client))
    print("✅ ChatHandler Cog 동적 로드 완료")