"""
감정 리액션 Cog (v1.0)

메시지 수신 시 감정을 분석해 이모지 리액션을 자동으로 추가합니다.

[설계]
- 리액션 대상: 사용자 메시지 + 봇 응답 메시지
- ON/OFF: reaction_enabled 플래그 (기본 ON)
- 쿨다운: 유저별 3초 (중복 분석 방지)
- 비동기: asyncio.to_thread()로 blocking 방지
- 독립 실행: ChatHandler와 별도 on_message 리스너로 충돌 없음
- 실패 시: 조용히 스킵 (봇 대화 흐름 블로킹 금지)

[슬래시 커맨드]
- /reaction on   : 리액션 기능 켜기
- /reaction off  : 리액션 기능 끄기
- /reaction status: 현재 상태 확인
"""
import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import time
from typing import Dict

from config.settings import CHANNEL_BOT
from utils.emotion_analyzer import EmotionAnalyzer


class ReactionHandler(commands.Cog):
    """감정 분석 + 이모지 리액션 자동 추가 Cog"""

    COOLDOWN_SECONDS = 3.0   # 같은 유저의 연속 메시지 쿨다운

    def __init__(self, bot: commands.Bot, emotion_analyzer: EmotionAnalyzer):
        self.bot              = bot
        self.analyzer         = emotion_analyzer
        self.reaction_enabled = True                    # 기본값: ON
        self._last_analyzed:  Dict[int, float] = {}    # user_id → timestamp

    # ------------------------------------------------------------------ #
    #  내부 헬퍼
    # ------------------------------------------------------------------ #
    def _is_cooldown(self, user_id: int) -> bool:
        """쿨다운 중이면 True"""
        last = self._last_analyzed.get(user_id, 0.0)
        return (time.monotonic() - last) < self.COOLDOWN_SECONDS

    def _update_cooldown(self, user_id: int):
        self._last_analyzed[user_id] = time.monotonic()

    async def _add_reactions(self, message: discord.Message, emojis: list[str]):
        """이모지 리스트를 순서대로 리액션 추가 (실패 시 개별 스킵)"""
        for emoji in emojis:
            try:
                await message.add_reaction(emoji)
            except discord.HTTPException as e:
                print(f"⚠️ 리액션 추가 실패 ({emoji}): {e}")

    # ------------------------------------------------------------------ #
    #  사용자 메시지 리액션
    # ------------------------------------------------------------------ #
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """사용자가 봇 채널에 메시지를 보낼 때 감정 분석 후 리액션"""
        # 봇 메시지, 다른 채널, 기능 꺼짐, 커맨드 제외
        if message.author.bot:
            return
        if message.channel.id != CHANNEL_BOT:
            return
        if not self.reaction_enabled:
            return
        if not message.content or message.content.startswith(('/', '!', '\\')):
            return

        user_id = message.author.id

        # 쿨다운 체크
        if self._is_cooldown(user_id):
            return
        self._update_cooldown(user_id)

        # 비동기 감정 분석 (메인 흐름 블로킹 방지)
        emojis = await asyncio.to_thread(self.analyzer.analyze, message.content)

        if emojis:
            await self._add_reactions(message, emojis)
            print(f"😊 리액션 추가: {emojis} → {message.author.name}: {message.content[:30]}")

    # ------------------------------------------------------------------ #
    #  봇 응답 메시지 리액션
    # ------------------------------------------------------------------ #
    async def react_to_bot_response(self, message: discord.Message):
        """
        봇 응답 메시지에 감정 리액션 추가.
        ChatHandler에서 send 후 직접 호출합니다.
        """
        if not self.reaction_enabled:
            return
        if not message.content:
            return

        emojis = await asyncio.to_thread(self.analyzer.analyze, message.content)

        if emojis:
            await self._add_reactions(message, emojis)
            print(f"🤖 봇 응답 리액션: {emojis} → {message.content[:30]}")

    # ------------------------------------------------------------------ #
    #  슬래시 커맨드
    # ------------------------------------------------------------------ #
    reaction_group = app_commands.Group(
        name="reaction",
        description="감정 리액션 자동 추가 기능 설정"
    )

    @reaction_group.command(name="on", description="감정 리액션 기능 켜기")
    async def reaction_on(self, interaction: discord.Interaction):
        self.reaction_enabled = True
        await interaction.response.send_message(
            "😊 감정 리액션 기능이 **켜졌습니다**!\n메시지 감정을 분석해 이모지 리액션을 자동으로 추가합니다.",
            ephemeral=True
        )
        print("✅ 감정 리액션 ON")

    @reaction_group.command(name="off", description="감정 리액션 기능 끄기")
    async def reaction_off(self, interaction: discord.Interaction):
        self.reaction_enabled = False
        await interaction.response.send_message(
            "😶 감정 리액션 기능이 **꺼졌습니다**.",
            ephemeral=True
        )
        print("⏹️ 감정 리액션 OFF")

    @reaction_group.command(name="status", description="감정 리액션 현재 상태 확인")
    async def reaction_status(self, interaction: discord.Interaction):
        status = "🟢 켜짐" if self.reaction_enabled else "🔴 꺼짐"
        embed = discord.Embed(
            title="😊 감정 리액션 설정",
            color=discord.Color.green() if self.reaction_enabled else discord.Color.red()
        )
        embed.add_field(name="현재 상태", value=status, inline=False)
        embed.add_field(
            name="동작 방식",
            value=(
                "• 사용자 메시지 감정 분석 후 이모지 리액션 추가\n"
                "• 봇 응답 메시지에도 감정 리액션 추가\n"
                f"• 쿨다운: {ReactionHandler.COOLDOWN_SECONDS}초"
            ),
            inline=False
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    """Cog 설정 함수 (동적 로드용)"""
    if not hasattr(bot, 'emotion_analyzer'):
        raise RuntimeError("bot.emotion_analyzer가 설정되지 않았습니다.")
    await bot.add_cog(ReactionHandler(bot, bot.emotion_analyzer))
    print("✅ ReactionHandler Cog 동적 로드 완료")