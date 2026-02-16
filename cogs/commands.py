"""
봇 텍스트 명령어 Cog (v2.2 - 아키텍처 수정)

[수정 내역]
- ARCH FIX: command_prefix가 '!'로 변경됨에 따라 모든 커맨드는 !명령어 형태로 동작.
- REMOVE: !model, !prompt 제거
  → 드롭다운 UI는 슬래시커맨드 전용(/model, /prompt). 중복 유지 불필요.
- KEEP: !temp, !topp, !split, !status, !reset, !memo, !초기화, !down
  → 슬래시커맨드에도 동일 기능이 있지만, 텍스트 채널에서 빠르게 쓰는 용도로 유지.
- UPDATE: 안내 메시지에서 '/' → '!' prefix 표기 수정.
"""
import discord
from discord.ext import commands
from datetime import timedelta

from config.settings import AVAILABLE_PROMPTS
from utils.gemini_client import GeminiClient
from utils.memo_manager import MemoManager


class BotCommands(commands.Cog):
    """봇 텍스트 명령어를 관리하는 Cog (!prefix 기반)"""

    def __init__(self, bot: commands.Bot, gemini_client: GeminiClient, chat_handler, memo_manager: MemoManager):
        self.bot = bot
        self.gemini_client = gemini_client
        self.chat_handler = chat_handler
        self.memo_manager = memo_manager

    # ========== 설정 ==========

    @commands.command(name='temp')
    async def set_temperature(self, ctx: commands.Context, value: float):
        """Temperature 설정 (0.0~2.0)"""
        if 0.0 <= value <= 2.0:
            self.gemini_client.update_settings(temperature=value)
            await ctx.send(f"🌡️ Temperature가 {value}로 설정되었습니다!")
        else:
            await ctx.send("❌ Temperature는 0.0 ~ 2.0 사이의 값이어야 합니다.")

    @commands.command(name='topp')
    async def set_top_p(self, ctx: commands.Context, value: float):
        """Top-p 설정 (0.0~1.0)"""
        if 0.0 <= value <= 1.0:
            self.gemini_client.update_settings(top_p=value)
            await ctx.send(f"🎯 Top-p가 {value}로 설정되었습니다!")
        else:
            await ctx.send("❌ Top-p는 0.0 ~ 1.0 사이의 값이어야 합니다.")

    # ========== Split ==========

    @commands.group(name='split', invoke_without_command=True)
    async def split_group(self, ctx: commands.Context):
        """분할 모드 명령어 그룹"""
        await ctx.send("사용법:\n• `!split on` - 분할 모드 켜기\n• `!split off` - 분할 모드 끄기")

    @split_group.command(name='on')
    async def split_on(self, ctx: commands.Context):
        self.chat_handler.set_split_mode(True)
        await ctx.send("✂️ 분할 모드가 켜졌습니다!")

    @split_group.command(name='off')
    async def split_off(self, ctx: commands.Context):
        self.chat_handler.set_split_mode(False)
        await ctx.send("📝 분할 모드가 꺼졌습니다!")

    # ========== 상태 확인 ==========

    @commands.command(name='status')
    async def show_status(self, ctx: commands.Context):
        """봇 상태 확인"""
        split_status = "🟢 켜짐" if self.chat_handler.split_mode else "🔴 꺼짐"
        current_file = self.gemini_client.current_prompt_file
        current_prompt = next(
            (p['name'] for p in AVAILABLE_PROMPTS if p['file'] == current_file), "Unknown"
        )
        embed = discord.Embed(title="⚙️ 봇 현재 설정", color=discord.Color.blue())
        embed.add_field(
            name="🤖 모델 설정",
            value=(
                f"**모델:** `{self.gemini_client.model_name}`\n"
                f"**프롬프트:** `{current_prompt}`\n"
                f"**Temperature:** `{self.gemini_client.temperature}`\n"
                f"**Top-p:** `{self.gemini_client.top_p}`"
            ),
            inline=False
        )
        embed.add_field(
            name="💬 대화 설정",
            value=f"**분할 모드:** {split_status}\n**저장된 메모:** {self.memo_manager.get_memory_count()}개",
            inline=False
        )
        embed.set_footer(text="💡 모델·프롬프트 변경은 슬래시커맨드 /model /prompt 를 사용하세요.")
        await ctx.send(embed=embed)

    # ========== 히스토리 초기화 ==========

    @commands.command(name='reset')
    @commands.has_permissions(administrator=True)
    async def reset_history(self, ctx: commands.Context):
        """전체 대화 히스토리 초기화 (관리자 전용)"""
        stats = self.chat_handler.get_user_stats()
        total_users = stats['total_users']
        total_messages = sum(u['message_count'] for u in stats['users'])

        if total_users == 0:
            await ctx.send("📝 초기화할 대화 히스토리가 없습니다.")
            return

        self.chat_handler.clear_history()
        embed = discord.Embed(
            title="🗑️ 전체 히스토리 초기화 완료",
            description=(
                f"**{total_users}명** 의 대화 히스토리가 삭제되었습니다.\n"
                f"삭제된 메시지 수: **{total_messages}개**"
            ),
            color=discord.Color.red()
        )
        embed.set_footer(text=f"요청자: {ctx.author.name}")
        await ctx.send(embed=embed)

    # ========== 메모 ==========

    @commands.group(name='memo', invoke_without_command=True)
    async def memo_group(self, ctx: commands.Context):
        """메모 명령어 그룹"""
        await ctx.send(
            "**🧠 메모 명령어:**\n"
            "• `!memo add <내용>`\n"
            "• `!memo delete <ID/내용>`\n"
            "• `!memo list`\n"
            "• `!memo search <키워드>`\n"
            "• `!memo clear` (관리자)"
        )

    @memo_group.command(name='add')
    async def memo_add(self, ctx: commands.Context, *, content: str):
        memory = self.memo_manager.add_memory(content, ctx.author.name)
        self.gemini_client.update_memories(self.memo_manager.get_memories_as_text())
        embed = discord.Embed(
            title="✅ 메모 추가!",
            description=f"**#{memory['id']}** {memory['content']}",
            color=discord.Color.green()
        )
        embed.set_footer(text=f"추가: {memory['date']} by {memory['added_by']}")
        await ctx.send(embed=embed)

    @memo_group.command(name='delete')
    async def memo_delete(self, ctx: commands.Context, *, content: str):
        deleted = (
            self.memo_manager.delete_memory_by_id(int(content))
            if content.isdigit()
            else self.memo_manager.delete_memory(content)
        )
        if deleted:
            self.gemini_client.update_memories(self.memo_manager.get_memories_as_text())
            embed = discord.Embed(
                title="🗑️ 메모 삭제!",
                description=f"**#{deleted['id']}** {deleted['content']}",
                color=discord.Color.orange()
            )
            await ctx.send(embed=embed)
        else:
            await ctx.send(f"❌ '{content}'와 일치하는 메모를 찾을 수 없습니다.")

    @memo_group.command(name='list')
    async def memo_list(self, ctx: commands.Context, page: int = 1):
        memories = self.memo_manager.get_all_memories()
        if not memories:
            await ctx.send("📝 아직 저장된 메모가 없습니다.")
            return
        items_per_page = 10
        total_pages = (len(memories) + items_per_page - 1) // items_per_page
        page = max(1, min(page, total_pages))
        page_memories = memories[(page - 1) * items_per_page: page * items_per_page]
        embed = discord.Embed(
            title=f"🧠 땅콩의 취향과 기억 ({len(memories)}개)",
            color=discord.Color.blue()
        )
        for m in page_memories:
            embed.add_field(
                name=f"#{m['id']} - {m['date']}",
                value=f"{m['content']}\n└ by {m['added_by']}",
                inline=False
            )
        embed.set_footer(text=f"페이지 {page}/{total_pages}")
        await ctx.send(embed=embed)

    @memo_group.command(name='search')
    async def memo_search(self, ctx: commands.Context, *, keyword: str):
        results = self.memo_manager.search_memories(keyword)
        if not results:
            await ctx.send(f"🔍 '{keyword}'와 관련된 메모를 찾을 수 없습니다.")
            return
        embed = discord.Embed(
            title=f"🔍 검색 결과: '{keyword}' ({len(results)}개)",
            color=discord.Color.purple()
        )
        for m in results:
            embed.add_field(
                name=f"#{m['id']} - {m['date']}",
                value=f"{m['content']}\n└ by {m['added_by']}",
                inline=False
            )
        await ctx.send(embed=embed)

    @memo_group.command(name='clear')
    @commands.has_permissions(administrator=True)
    async def memo_clear(self, ctx: commands.Context):
        count = self.memo_manager.clear_all_memories()
        self.gemini_client.update_memories("")
        embed = discord.Embed(
            title="🗑️ 모든 메모 삭제!",
            description=f"총 {count}개 삭제됨.",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)

    # ========== 초기화 ==========

    @commands.command(name='초기화')
    async def reset_context(self, ctx: commands.Context):
        """내 대화 내역 초기화"""
        user_id = ctx.author.id
        history_count = len(self.chat_handler.get_conversation_history(user_id))
        self.chat_handler.clear_history(user_id)
        embed = discord.Embed(
            title="🔄 초기화 완료",
            description=(
                f"🗑️ 대화 내역 **{history_count}개** 삭제\n"
                "✅ 컨텍스트가 완전히 초기화되었습니다. 새로운 대화를 시작하세요!"
            ),
            color=discord.Color.orange()
        )
        await ctx.send(embed=embed)

    # ========== 봇 종료 ==========

    @commands.command(name='down')
    @commands.has_permissions(administrator=True)
    async def shutdown(self, ctx: commands.Context):
        """봇 종료 (관리자 전용)"""
        embed = discord.Embed(
            title="⏹️ 봇 종료",
            description="공책봇이 종료됩니다. 잠시 후 오프라인 상태가 됩니다.",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)
        print(f"⏹️ !down 명령어로 봇 종료 (요청자: {ctx.author.name})")
        await self.bot.close()


async def setup(bot: commands.Bot):
    """Cog 설정 함수 (동적 로드용)"""
    if not hasattr(bot, 'gemini_client'):
        raise RuntimeError("bot.gemini_client가 설정되지 않았습니다.")
    if not hasattr(bot, 'chat_handler'):
        raise RuntimeError("bot.chat_handler가 설정되지 않았습니다.")
    if not hasattr(bot, 'memo_manager'):
        raise RuntimeError("bot.memo_manager가 설정되지 않았습니다.")
    await bot.add_cog(BotCommands(bot, bot.gemini_client, bot.chat_handler, bot.memo_manager))
    print("✅ BotCommands Cog 동적 로드 완료")