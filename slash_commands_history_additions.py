# slash_commands.py에 추가할 명령어들

# ========== 히스토리 관리 명령어 (추가) ==========

history_group = app_commands.Group(name="history", description="대화 히스토리 관리")

@history_group.command(name="view", description="내 대화 히스토리 확인")
async def history_view(self, interaction: discord.Interaction):
    """사용자의 대화 히스토리 확인"""
    user_id = interaction.user.id
    history = self.chat_handler.get_conversation_history(user_id)
    
    if not history:
        await interaction.response.send_message(
            "📝 아직 대화 히스토리가 없습니다.",
            ephemeral=True
        )
        return
    
    embed = discord.Embed(
        title="💬 내 대화 히스토리",
        description=f"총 **{len(history)}개**의 메시지",
        color=discord.Color.blue()
    )
    
    # 최근 5개만 표시
    recent_messages = history[-5:]
    for i, msg in enumerate(recent_messages, 1):
        role = "🙋 나" if msg["role"] == "user" else "🤖 공책봇"
        content = msg["parts"][0]["text"]
        
        # 길면 자르기
        if len(content) > 100:
            content = content[:100] + "..."
        
        embed.add_field(
            name=f"{role} (#{len(history) - 5 + i})",
            value=content,
            inline=False
        )
    
    if len(history) > 5:
        embed.set_footer(text=f"최근 5개만 표시 (전체: {len(history)}개)")
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@history_group.command(name="clear", description="내 대화 히스토리 삭제")
async def history_clear(self, interaction: discord.Interaction):
    """사용자의 대화 히스토리 초기화"""
    user_id = interaction.user.id
    
    history = self.chat_handler.get_conversation_history(user_id)
    count = len(history)
    
    if count == 0:
        await interaction.response.send_message(
            "📝 삭제할 대화 히스토리가 없습니다.",
            ephemeral=True
        )
        return
    
    self.chat_handler.clear_history(user_id)
    
    embed = discord.Embed(
        title="🗑️ 대화 히스토리 삭제 완료",
        description=f"총 **{count}개**의 메시지가 삭제되었습니다.",
        color=discord.Color.orange()
    )
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@history_group.command(name="stats", description="전체 사용자 통계 (관리자 전용)")
@app_commands.default_permissions(administrator=True)
async def history_stats(self, interaction: discord.Interaction):
    """전체 사용자 통계"""
    stats = self.chat_handler.get_user_stats()
    
    embed = discord.Embed(
        title="📊 대화 히스토리 통계",
        color=discord.Color.purple()
    )
    
    embed.add_field(
        name="전체 사용자",
        value=f"**{stats['total_users']}명**",
        inline=True
    )
    
    total_messages = sum(u["message_count"] for u in stats["users"])
    embed.add_field(
        name="전체 메시지",
        value=f"**{total_messages}개**",
        inline=True
    )
    
    # 상위 5명
    top_users = sorted(stats["users"], key=lambda x: x["message_count"], reverse=True)[:5]
    
    if top_users:
        top_list = "\n".join([
            f"<@{u['user_id']}>: {u['message_count']}개"
            for u in top_users
        ])
        
        embed.add_field(
            name="🏆 상위 사용자",
            value=top_list,
            inline=False
        )
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ========== 기존 /status 명령어 업데이트 ==========

@app_commands.command(name="status", description="현재 봇 설정 확인")
async def status(self, interaction: discord.Interaction):
    """봇 상태 확인 (사용자별 정보 포함)"""
    user_id = interaction.user.id
    split_status = "🟢 켜짐" if self.chat_handler.split_mode else "🔴 꺼짐"
    
    # 사용자별 히스토리
    user_history = self.chat_handler.get_conversation_history(user_id)
    user_history_count = len(user_history)
    
    # 전체 통계
    stats = self.chat_handler.get_user_stats()
    
    memo_count = self.memo_manager.get_memory_count()
    
    # 현재 프롬프트 이름 찾기
    current_file = self.gemini_client.current_prompt_file
    current_prompt = "Unknown"
    for prompt in AVAILABLE_PROMPTS:
        if prompt['file'] == current_file:
            current_prompt = prompt['name']
            break
    
    embed = discord.Embed(
        title="⚙️ 봇 현재 설정",
        color=discord.Color.blue()
    )
    
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
        value=(
            f"**분할 모드:** {split_status}\n"
            f"**저장된 메모:** {memo_count}개"
        ),
        inline=False
    )
    
    # 🆕 사용자별 히스토리
    embed.add_field(
        name="📚 내 히스토리",
        value=(
            f"**내 대화:** {user_history_count}개 메시지\n"
            f"**전체 사용자:** {stats['total_users']}명"
        ),
        inline=False
    )
    
    # 프롬프트 생성 세션 정보
    active_sessions = self.session_manager.get_active_sessions_count()
    embed.add_field(
        name="🔧 프롬프트 생성",
        value=f"**활성 세션:** {active_sessions}개",
        inline=False
    )
    
    await interaction.response.send_message(embed=embed)

# ========== /reset 명령어 업데이트 ==========

@app_commands.command(name="reset", description="대화 히스토리 초기화")
@app_commands.describe(
    scope="초기화 범위 (자신/전체)"
)
@app_commands.choices(scope=[
    app_commands.Choice(name="내 히스토리만", value="self"),
    app_commands.Choice(name="전체 히스토리 (관리자)", value="all")
])
async def reset(self, interaction: discord.Interaction, scope: str = "self"):
    """대화 히스토리 초기화"""
    user_id = interaction.user.id
    
    if scope == "self":
        # 자신의 히스토리만 초기화
        history = self.chat_handler.get_conversation_history(user_id)
        count = len(history)
        
        if count == 0:
            await interaction.response.send_message(
                "📝 삭제할 대화 히스토리가 없습니다.",
                ephemeral=True
            )
            return
        
        self.chat_handler.clear_history(user_id)
        await interaction.response.send_message(
            f"🗑️ 내 대화 히스토리가 초기화되었습니다! ({count}개 메시지 삭제)",
            ephemeral=True
        )
    
    elif scope == "all":
        # 관리자 권한 확인
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "❌ 전체 히스토리 초기화는 관리자만 가능합니다.",
                ephemeral=True
            )
            return
        
        stats = self.chat_handler.get_user_stats()
        total_users = stats['total_users']
        
        self.chat_handler.clear_history(None)  # 전체 초기화
        
        await interaction.response.send_message(
            f"🗑️ 모든 사용자의 대화 히스토리가 초기화되었습니다! ({total_users}명)",
            ephemeral=True
        )