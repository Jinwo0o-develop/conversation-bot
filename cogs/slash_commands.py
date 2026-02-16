"""
Discord 슬래시 커맨드 Cog (v3.4 - 레퍼런스 이미지 스타일 드롭다운)

[수정 내역]
- REDESIGN: /model 드롭다운을 레퍼런스 이미지 스타일로 전면 재설계
  · embed 제거 → 심플한 텍스트 메시지 + 드롭다운만 표시
  · "현재 LLM 모델: **모델명**" 형태로 현재 선택 표시
  · placeholder = 현재 선택된 모델명 (체크마크로 default 표시)
  · 각 항목: 이모지 + 모델명 + 특성 설명 (description 줄)
  · 선택 즉시 메시지 텍스트 업데이트 (닫기 버튼 제거)
- REDESIGN: /prompt 동일 스타일 적용
"""
import discord
from discord import app_commands
from discord.ext import commands
from datetime import timedelta
from typing import List

from config.settings import AVAILABLE_MODELS, AVAILABLE_PROMPTS
from utils.gemini_client import GeminiClient
from utils.memo_manager import MemoManager


# ========== 모델별 메타 정보 ==========
# (이모지, description 줄에 표시될 특성 설명)

MODEL_META = {
    'gemini-3-pro-preview':   ('🔮', '최고 성능 · 복잡한 추론 특화'),
    'gemini-2.5-flash':       ('🤖', '빠른 응답 · 균형 잡힌 성능'),
    'gemini-3-flash-preview': ('🤖', '차세대 Flash · 속도+품질 향상'),
    'gemini-2.5-flash-lite':  ('🤖', '초경량 · 가장 빠른 응답속도'),
}

PROMPT_META = {
    'Ultimate': ('🌟', '땅콩의 완전한 성격과 모든 특성'),
    'Optimize': ('⚙️', '토큰 효율 최적화 · 간결한 응답'),
}


# ========== 모델 선택 드롭다운 ==========

class ModelSelectDropdown(discord.ui.Select):
    """
    레퍼런스 스타일 모델 선택 드롭다운
    - placeholder: 현재 선택된 모델명 표시
    - 각 옵션: 이모지 + 모델명 (label) + 특성 설명 (description)
    - default=True 인 항목에 체크마크(✓) 자동 표시
    """

    def __init__(self, gemini_client: GeminiClient):
        self.gemini_client = gemini_client
        current_model = gemini_client.model_name

        options = []
        for model in AVAILABLE_MODELS:
            emoji, desc = MODEL_META.get(model, ('🤖', ''))
            options.append(
                discord.SelectOption(
                    label=model,
                    value=model,
                    description=desc,
                    emoji=emoji,
                    default=(model == current_model)
                )
            )

        super().__init__(
            placeholder=current_model,   # 현재 모델명을 placeholder로 표시
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        selected_model = self.values[0]
        self.gemini_client.update_settings(model_name=selected_model)

        # 선택 항목 default 업데이트 & placeholder 갱신
        for option in self.options:
            option.default = (option.value == selected_model)
        self.placeholder = selected_model

        emoji, _ = MODEL_META.get(selected_model, ('🤖', ''))
        await interaction.response.edit_message(
            content=f"현재 LLM 모델: **{selected_model}**\n변경할 모델을 선택해 주세요.",
            view=self.view
        )


class ModelSelectView(discord.ui.View):
    def __init__(self, gemini_client: GeminiClient):
        super().__init__(timeout=120)
        self.add_item(ModelSelectDropdown(gemini_client))

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True


# ========== 프롬프트 선택 드롭다운 ==========

class PromptSelectDropdown(discord.ui.Select):
    """
    레퍼런스 스타일 프롬프트 선택 드롭다운
    - placeholder: 현재 선택된 프롬프트명 표시
    - 각 옵션: 이모지 + 프롬프트명 (label) + 특성 설명 (description)
    - 선택 즉시 히스토리 초기화 + 메시지 업데이트
    """

    def __init__(self, gemini_client: GeminiClient, memo_manager, chat_handler):
        self.gemini_client = gemini_client
        self.memo_manager = memo_manager
        self.chat_handler = chat_handler
        current_file = gemini_client.current_prompt_file
        current_name = next(
            (p['name'] for p in AVAILABLE_PROMPTS if p['file'] == current_file), '프롬프트 선택'
        )

        options = []
        for i, p in enumerate(AVAILABLE_PROMPTS):
            emoji, meta_desc = PROMPT_META.get(p['name'], ('📝', ''))
            display_desc = (p.get('description') or meta_desc)[:100]
            options.append(
                discord.SelectOption(
                    label=p['name'],
                    value=str(i),
                    description=display_desc,
                    emoji=emoji,
                    default=(p['file'] == current_file)
                )
            )

        super().__init__(
            placeholder=current_name,    # 현재 프롬프트명을 placeholder로 표시
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        index = int(self.values[0])
        prompt_info = AVAILABLE_PROMPTS[index]
        success = self.gemini_client.load_system_prompt(prompt_info['file'])

        if success:
            self.gemini_client.update_memories(self.memo_manager.get_memories_as_text())
            self.chat_handler.clear_history()

            for option in self.options:
                option.default = (option.value == self.values[0])
            self.placeholder = prompt_info['name']

            await interaction.response.edit_message(
                content=(
                    f"현재 프롬프트: **{prompt_info['name']}**\n"
                    f"변경할 프롬프트를 선택해 주세요. *(변경 시 대화 히스토리 초기화)*"
                ),
                view=self.view
            )
        else:
            await interaction.response.send_message(
                f"❌ 프롬프트 파일 로드 실패: `{prompt_info['file']}`", ephemeral=True
            )


class PromptSelectView(discord.ui.View):
    def __init__(self, gemini_client: GeminiClient, memo_manager, chat_handler):
        super().__init__(timeout=120)
        self.add_item(PromptSelectDropdown(gemini_client, memo_manager, chat_handler))

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True


class SlashCommands(commands.Cog):
    """슬래시 커맨드를 관리하는 Cog"""
    
    def __init__(self, bot: commands.Bot, gemini_client: GeminiClient, chat_handler, memo_manager: MemoManager):
        self.bot = bot
        self.gemini_client = gemini_client
        self.chat_handler = chat_handler
        self.memo_manager = memo_manager
    
    # ========== 설정 명령어 ==========
    
    @app_commands.command(name="temp", description="Temperature 설정 (0.0~2.0)")
    @app_commands.describe(value="Temperature 값 (0.0~2.0)")
    async def temp(self, interaction: discord.Interaction, value: float):
        if 0.0 <= value <= 2.0:
            self.gemini_client.update_settings(temperature=value)
            await interaction.response.send_message(f"🌡️ Temperature가 {value}로 설정되었습니다!", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Temperature는 0.0 ~ 2.0 사이의 값이어야 합니다.", ephemeral=True)
    
    @app_commands.command(name="topp", description="Top-p 설정 (0.0~1.0)")
    @app_commands.describe(value="Top-p 값 (0.0~1.0)")
    async def topp(self, interaction: discord.Interaction, value: float):
        if 0.0 <= value <= 1.0:
            self.gemini_client.update_settings(top_p=value)
            await interaction.response.send_message(f"🎯 Top-p가 {value}로 설정되었습니다!", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Top-p는 0.0 ~ 1.0 사이의 값이어야 합니다.", ephemeral=True)
    
    # ========== 모델 명령어 (view + select 통합) ==========

    @app_commands.command(name="model", description="AI 모델 목록 확인 및 변경 (드롭다운)")
    async def model_select(self, interaction: discord.Interaction):
        current_model = self.gemini_client.model_name
        view = ModelSelectView(self.gemini_client)
        await interaction.response.send_message(
            content=f"현재 LLM 모델: **{current_model}**\n변경할 모델을 선택해 주세요.",
            view=view,
            ephemeral=True
        )
    
    # ========== Split 명령어 ==========
    
    split_group = app_commands.Group(name="split", description="답변 분할 모드")
    
    @split_group.command(name="on", description="답변을 3개로 나눠서 전송")
    async def split_on(self, interaction: discord.Interaction):
        self.chat_handler.set_split_mode(True)
        await interaction.response.send_message("✂️ 분할 모드가 켜졌습니다!", ephemeral=True)
    
    @split_group.command(name="off", description="일반 답변으로 전송")
    async def split_off(self, interaction: discord.Interaction):
        self.chat_handler.set_split_mode(False)
        await interaction.response.send_message("📝 분할 모드가 꺼졌습니다!", ephemeral=True)
    
    # ========== 프롬프트 명령어 ==========

    @app_commands.command(name="prompt", description="프롬프트 목록 확인 및 변경 (드롭다운)")
    async def prompt_select(self, interaction: discord.Interaction):
        current_file = self.gemini_client.current_prompt_file
        current_name = next(
            (p['name'] for p in AVAILABLE_PROMPTS if p['file'] == current_file), "Unknown"
        )
        view = PromptSelectView(self.gemini_client, self.memo_manager, self.chat_handler)
        await interaction.response.send_message(
            content=(
                f"현재 프롬프트: **{current_name}**\n"
                f"변경할 프롬프트를 선택해 주세요. *(변경 시 대화 히스토리 초기화)*"
            ),
            view=view,
            ephemeral=True
        )
    
    # ========== 🆕 히스토리 관리 명령어 ==========
    
    history_group = app_commands.Group(name="history", description="대화 히스토리 관리")
    
    @history_group.command(name="view", description="내 대화 히스토리 확인")
    async def history_view(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        history = self.chat_handler.get_conversation_history(user_id)
        
        if not history:
            await interaction.response.send_message("📝 아직 대화 히스토리가 없습니다.", ephemeral=True)
            return
        
        embed = discord.Embed(title="💬 내 대화 히스토리", description=f"총 **{len(history)}개**의 메시지", color=discord.Color.blue())
        
        recent = history[-5:]
        for i, msg in enumerate(recent, 1):
            role = "🙋 나" if msg["role"] == "user" else "🤖 공책봇"
            content = msg["parts"][0]["text"]
            if len(content) > 100:
                content = content[:100] + "..."
            embed.add_field(name=f"{role} (#{len(history) - 5 + i})", value=content, inline=False)
        
        if len(history) > 5:
            embed.set_footer(text=f"최근 5개만 표시 (전체: {len(history)}개)")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @history_group.command(name="clear", description="내 대화 히스토리 삭제")
    async def history_clear(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        history = self.chat_handler.get_conversation_history(user_id)
        count = len(history)
        
        if count == 0:
            await interaction.response.send_message("📝 삭제할 대화 히스토리가 없습니다.", ephemeral=True)
            return
        
        self.chat_handler.clear_history(user_id)
        embed = discord.Embed(title="🗑️ 대화 히스토리 삭제 완료", description=f"총 **{count}개**의 메시지가 삭제되었습니다.", color=discord.Color.orange())
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    @history_group.command(name="stats", description="전체 사용자 통계 (관리자 전용)")
    @app_commands.default_permissions(administrator=True)
    async def history_stats(self, interaction: discord.Interaction):
        stats = self.chat_handler.get_user_stats()
        total_messages = sum(u["message_count"] for u in stats["users"])
        top_users = sorted(stats["users"], key=lambda x: x["message_count"], reverse=True)[:5]
        
        embed = discord.Embed(title="📊 대화 히스토리 통계", color=discord.Color.purple())
        embed.add_field(name="전체 사용자", value=f"**{stats['total_users']}명**", inline=True)
        embed.add_field(name="전체 메시지", value=f"**{total_messages}개**", inline=True)
        
        if top_users:
            embed.add_field(
                name="🏆 상위 사용자",
                value="\n".join([f"<@{u['user_id']}>: {u['message_count']}개" for u in top_users]),
                inline=False
            )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
    
    # ========== 메모 명령어 ==========
    
    memo_group = app_commands.Group(name="memo", description="땅콩의 취향과 기억 관리")
    
    @memo_group.command(name="add", description="새로운 취향/기억 추가")
    @app_commands.describe(content="추가할 내용")
    async def memo_add(self, interaction: discord.Interaction, content: str):
        memory = self.memo_manager.add_memory(content, interaction.user.name)
        self.gemini_client.update_memories(self.memo_manager.get_memories_as_text())
        
        embed = discord.Embed(title="✅ 메모 추가!", description=f"**#{memory['id']}** {memory['content']}", color=discord.Color.green())
        embed.set_footer(text=f"추가: {memory['date']} by {memory['added_by']}")
        await interaction.response.send_message(embed=embed)
    
    @memo_group.command(name="delete", description="메모 삭제")
    @app_commands.describe(content="삭제할 메모 ID 또는 내용")
    async def memo_delete(self, interaction: discord.Interaction, content: str):
        deleted = self.memo_manager.delete_memory_by_id(int(content)) if content.isdigit() else self.memo_manager.delete_memory(content)
        
        if deleted:
            self.gemini_client.update_memories(self.memo_manager.get_memories_as_text())
            embed = discord.Embed(title="🗑️ 메모 삭제!", description=f"**#{deleted['id']}** {deleted['content']}", color=discord.Color.orange())
            await interaction.response.send_message(embed=embed)
        else:
            await interaction.response.send_message(f"❌ '{content}'와 일치하는 메모를 찾을 수 없습니다.", ephemeral=True)
    
    @memo_group.command(name="list", description="저장된 모든 메모 보기")
    @app_commands.describe(page="페이지 번호 (기본: 1)")
    async def memo_list(self, interaction: discord.Interaction, page: int = 1):
        memories = self.memo_manager.get_all_memories()
        if not memories:
            await interaction.response.send_message("📝 아직 저장된 메모가 없습니다.", ephemeral=True)
            return
        
        items_per_page = 10
        total_pages = (len(memories) + items_per_page - 1) // items_per_page
        page = max(1, min(page, total_pages))
        page_memories = memories[(page-1)*items_per_page : page*items_per_page]
        
        embed = discord.Embed(title=f"🧠 땅콩의 취향과 기억 ({len(memories)}개)", color=discord.Color.blue())
        for m in page_memories:
            embed.add_field(name=f"#{m['id']} - {m['date']}", value=f"{m['content']}\n└ by {m['added_by']}", inline=False)
        embed.set_footer(text=f"페이지 {page}/{total_pages}")
        await interaction.response.send_message(embed=embed)
    
    @memo_group.command(name="search", description="키워드로 메모 검색")
    @app_commands.describe(keyword="검색 키워드")
    async def memo_search(self, interaction: discord.Interaction, keyword: str):
        results = self.memo_manager.search_memories(keyword)
        if not results:
            await interaction.response.send_message(f"🔍 '{keyword}'와 관련된 메모를 찾을 수 없습니다.", ephemeral=True)
            return
        
        embed = discord.Embed(title=f"🔍 검색 결과: '{keyword}' ({len(results)}개)", color=discord.Color.purple())
        for m in results[:10]:
            embed.add_field(name=f"#{m['id']} - {m['date']}", value=f"{m['content']}\n└ by {m['added_by']}", inline=False)
        if len(results) > 10:
            embed.set_footer(text=f"총 {len(results)}개 중 10개만 표시됩니다.")
        await interaction.response.send_message(embed=embed)
    
    @memo_group.command(name="clear", description="모든 메모 삭제 (관리자 전용)")
    @app_commands.default_permissions(administrator=True)
    async def memo_clear(self, interaction: discord.Interaction):
        count = self.memo_manager.clear_all_memories()
        self.gemini_client.update_memories("")
        embed = discord.Embed(title="🗑️ 모든 메모 삭제!", description=f"총 {count}개 삭제됨.", color=discord.Color.red())
        await interaction.response.send_message(embed=embed)
    
    # ========== 기능 명령어 ==========
    
    @app_commands.command(name="summarize", description="대화 요약")
    @app_commands.describe(message_id="기준 메시지 ID", hours="몇 시간 전까지")
    async def summarize(self, interaction: discord.Interaction, message_id: str, hours: int):
        await interaction.response.defer()
        try:
            target = await interaction.channel.fetch_message(int(message_id))
            time_threshold = target.created_at - timedelta(hours=hours)
            
            messages = []
            async for msg in interaction.channel.history(limit=200, before=target.created_at):
                if msg.created_at >= time_threshold:
                    if not msg.author.bot and not msg.content.startswith(('/', '!', '\\')):
                        messages.append(f"{msg.author.name}: {msg.content}")
                else:
                    break
            
            messages.reverse()
            if not messages:
                await interaction.followup.send("❌ 요약할 대화가 없습니다.")
                return
            
            response_text = self.gemini_client.generate_response(f"다음 대화를 간단히 요약해주세요:\n\n" + "\n".join(messages))
            embed = discord.Embed(title=f"📝 최근 {hours}시간 대화 요약", description=response_text, color=discord.Color.green())
            embed.set_footer(text=f"총 {len(messages)}개 메시지 분석")
            await interaction.followup.send(embed=embed)
            
        except discord.NotFound:
            await interaction.followup.send("❌ 해당 메시지를 찾을 수 없습니다.")
        except ValueError:
            await interaction.followup.send("❌ 올바른 메시지 ID를 입력해주세요.")
        except Exception as e:
            await interaction.followup.send(f"❌ 오류: {e}")
    
    @app_commands.command(name="status", description="현재 봇 설정 확인")
    async def status(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        split_status = "🟢 켜짐" if self.chat_handler.split_mode else "🔴 꺼짐"
        user_history_count = len(self.chat_handler.get_conversation_history(user_id))
        stats = self.chat_handler.get_user_stats()
        current_file = self.gemini_client.current_prompt_file
        current_prompt = next((p['name'] for p in AVAILABLE_PROMPTS if p['file'] == current_file), "Unknown")
        
        embed = discord.Embed(title="⚙️ 봇 현재 설정", color=discord.Color.blue())
        embed.add_field(
            name="🤖 모델 설정",
            value=f"**모델:** `{self.gemini_client.model_name}`\n**프롬프트:** `{current_prompt}`\n**Temperature:** `{self.gemini_client.temperature}`\n**Top-p:** `{self.gemini_client.top_p}`",
            inline=False
        )
        embed.add_field(
            name="💬 대화 설정",
            value=f"**분할 모드:** {split_status}\n**저장된 메모:** {self.memo_manager.get_memory_count()}개",
            inline=False
        )
        embed.add_field(
            name="📚 내 히스토리",
            value=f"**내 대화:** {user_history_count}개 메시지\n**전체 사용자:** {stats['total_users']}명",
            inline=False
        )
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="command", description="사용 가능한 명령어 목록")
    async def command_list(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🤖 공책봇 명령어 목록",
            description="사용 가능한 모든 슬래시 커맨드입니다.",
            color=discord.Color.purple()
        )
        embed.add_field(
            name="⚙️ 설정",
            value=(
                "• `/temp <값>` - Temperature 설정 (0.0~2.0)\n"
                "• `/topp <값>` - Top-p 설정 (0.0~1.0)\n"
                "• `/model` - 모델 목록 확인 & 드롭다운 변경\n"
                "• `/prompt` - 프롬프트 목록 확인 & 드롭다운 변경\n"
                "• `/split on/off` - 답변 분할 모드"
            ),
            inline=False
        )
        embed.add_field(
            name="📚 대화 히스토리",
            value=(
                "• `/history view` - 내 대화 내역 확인\n"
                "• `/history clear` - 내 대화 내역 삭제\n"
                "• `/history stats` - 전체 통계 (관리자)\n"
                "• `/초기화` - 대화 내역 & 컨텍스트 초기화\n"
                "• `/reset` - 히스토리 초기화 (범위 선택)"
            ),
            inline=False
        )
        embed.add_field(
            name="🧠 메모",
            value=(
                "• `/memo add <내용>` - 메모 추가\n"
                "• `/memo delete <ID/내용>` - 메모 삭제\n"
                "• `/memo list` - 전체 메모 보기\n"
                "• `/memo search <키워드>` - 메모 검색\n"
                "• `/memo clear` - 전체 삭제 (관리자)"
            ),
            inline=False
        )
        embed.add_field(
            name="📊 기타",
            value=(
                "• `/summarize <메시지ID> <시간>` - 대화 요약\n"
                "• `/status` - 봇 현재 설정 확인\n"
                "• `/sync` - 슬래시 커맨드 동기화 (관리자)\n"
                "• `/down` - 봇 종료 (관리자)"
            ),
            inline=False
        )
        embed.set_footer(text="공책봇 v3.3 | 💡 백슬래시(\\)로 시작하는 메시지는 봇이 무시합니다.")
        await interaction.response.send_message(embed=embed)

    # ========== /초기화 ==========

    @app_commands.command(name="초기화", description="내 대화 내역 및 컨텍스트 전체 초기화")
    async def reset_context(self, interaction: discord.Interaction):
        """대화 히스토리 초기화"""
        user_id = interaction.user.id
        history_count = len(self.chat_handler.get_conversation_history(user_id))
        self.chat_handler.clear_history(user_id)

        embed = discord.Embed(
            title="🔄 초기화 완료",
            description=f"🗑️ 대화 내역 **{history_count}개** 삭제\n✅ 컨텍스트가 완전히 초기화되었습니다. 새로운 대화를 시작하세요!",
            color=discord.Color.orange()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ========== /down ==========

    @app_commands.command(name="down", description="봇 종료 (관리자 전용)")
    @app_commands.default_permissions(administrator=True)
    async def shutdown(self, interaction: discord.Interaction):
        """봇을 안전하게 종료"""
        embed = discord.Embed(
            title="⏹️ 봇 종료",
            description="공책봇이 종료됩니다. 잠시 후 오프라인 상태가 됩니다.",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed)
        print(f"⏹️ /down 명령어로 봇 종료 (요청자: {interaction.user.name})")
        await self.bot.close()
    
    @app_commands.command(name="reset", description="대화 히스토리 초기화")
    @app_commands.describe(scope="초기화 범위")
    @app_commands.choices(scope=[
        app_commands.Choice(name="내 히스토리만", value="self"),
        app_commands.Choice(name="전체 히스토리 (관리자)", value="all")
    ])
    async def reset(self, interaction: discord.Interaction, scope: str = "self"):
        user_id = interaction.user.id
        
        if scope == "self":
            history = self.chat_handler.get_conversation_history(user_id)
            count = len(history)
            if count == 0:
                await interaction.response.send_message("📝 삭제할 히스토리가 없습니다.", ephemeral=True)
                return
            self.chat_handler.clear_history(user_id)
            await interaction.response.send_message(f"🗑️ 내 히스토리가 초기화되었습니다! ({count}개 삭제)", ephemeral=True)
        
        elif scope == "all":
            if not interaction.user.guild_permissions.administrator:
                await interaction.response.send_message("❌ 전체 초기화는 관리자만 가능합니다.", ephemeral=True)
                return
            total_users = self.chat_handler.get_user_stats()['total_users']
            self.chat_handler.clear_history(None)
            await interaction.response.send_message(f"🗑️ 모든 사용자의 히스토리가 초기화되었습니다! ({total_users}명)", ephemeral=True)
    
    @app_commands.command(name="sync", description="슬래시 커맨드 전체 초기화 후 재동기화 (관리자 전용)")
    @app_commands.default_permissions(administrator=True)
    async def sync_commands(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            # 기존 등록된 명령어 전체 삭제 후 재동기화
            self.bot.tree.clear_commands(guild=None)
            synced = await self.bot.tree.sync()
            embed = discord.Embed(
                title="✅ 슬래시 커맨드 재동기화 완료",
                description=f"기존 명령어를 전부 제거하고 **{len(synced)}개** 명령어를 새로 등록했습니다.",
                color=discord.Color.green()
            )
            command_list = "\n".join([f"• `/{cmd.name}`" for cmd in synced[:20]])
            if len(synced) > 20:
                command_list += f"\n... 외 {len(synced) - 20}개"
            embed.add_field(name="등록된 명령어", value=command_list, inline=False)
            embed.set_footer(text="⚠️ Discord 반영까지 최대 1시간 소요될 수 있습니다.")
            await interaction.followup.send(embed=embed, ephemeral=True)
            print(f"✅ 슬래시 커맨드 수동 재동기화: {len(synced)}개")
        except Exception as e:
            embed = discord.Embed(title="❌ 동기화 실패", description=f"오류: {str(e)}", color=discord.Color.red())
            await interaction.followup.send(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    """Cog 설정 함수 (동적 로드용)"""
    if not hasattr(bot, 'gemini_client'):
        raise RuntimeError("bot.gemini_client가 설정되지 않았습니다.")
    if not hasattr(bot, 'chat_handler'):
        raise RuntimeError("bot.chat_handler가 설정되지 않았습니다.")
    if not hasattr(bot, 'memo_manager'):
        raise RuntimeError("bot.memo_manager가 설정되지 않았습니다.")
    
    await bot.add_cog(SlashCommands(bot, bot.gemini_client, bot.chat_handler, bot.memo_manager))
    print("✅ SlashCommands Cog 동적 로드 완료")