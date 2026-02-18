"""
스케줄러 Cog (v1.0)

예약 메시지 기능을 제공합니다.

[기능]
- /schedule add <시간> <메시지>  — 지정 시간에 메시지 자동 전송
- /schedule list                — 등록된 예약 목록 확인
- /schedule delete <ID>         — 예약 삭제

[시간 형식]
- YYYY-MM-DD HH:MM  (예: 2026-02-20 09:00)
- HH:MM             (예: 07:00 — 오늘 또는 내일)

[저장 구조]
data/schedules.json:
{
  "schedules": [
    {
      "id": 1,
      "channel_id": 1234567890,
      "user_id": 9876543210,
      "time": "2026-02-20T09:00:00",
      "message": "좋은 아침!",
      "created_at": "2026-02-19T14:30:00",
      "repeats": false
    }
  ]
}
"""
import discord
from discord import app_commands
from discord.ext import commands, tasks
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import json
import os

SCHEDULE_FILE = "data/schedules.json"


class ScheduleManager:
    """예약 메시지 관리 클래스 (JSON 기반 영속화)"""

    def __init__(self, filepath: str = SCHEDULE_FILE):
        self.filepath = filepath
        self.schedules: List[Dict] = []
        self.load()

    def load(self):
        """파일에서 예약 목록 로드"""
        os.makedirs(os.path.dirname(self.filepath), exist_ok=True)
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.schedules = data.get("schedules", [])
                print(f"✅ 스케줄 로드 완료: {len(self.schedules)}개")
            except Exception as e:
                print(f"⚠️ 스케줄 파일 로드 실패: {e}")
                self.schedules = []
        else:
            self.schedules = []

    def save(self):
        """파일에 예약 목록 저장"""
        try:
            with open(self.filepath, 'w', encoding='utf-8') as f:
                json.dump({"schedules": self.schedules}, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"❌ 스케줄 저장 실패: {e}")

    def _next_id(self) -> int:
        """새 예약 ID 생성"""
        if not self.schedules:
            return 1
        return max(s['id'] for s in self.schedules) + 1

    def add(self, channel_id: int, user_id: int, time: datetime, message: str, repeats: bool = False) -> Dict:
        """새 예약 추가"""
        schedule = {
            "id": self._next_id(),
            "channel_id": channel_id,
            "user_id": user_id,
            "time": time.isoformat(),
            "message": message,
            "created_at": datetime.now().isoformat(),
            "repeats": repeats
        }
        self.schedules.append(schedule)
        self.save()
        return schedule

    def delete(self, schedule_id: int, user_id: int) -> Optional[Dict]:
        """예약 삭제 (본인 또는 관리자만)"""
        for s in self.schedules:
            if s['id'] == schedule_id:
                # 본인 확인 (관리자 권한 체크는 호출부에서)
                if s['user_id'] != user_id:
                    return None
                self.schedules.remove(s)
                self.save()
                return s
        return None

    def get_all(self, user_id: Optional[int] = None) -> List[Dict]:
        """예약 목록 조회 (user_id 지정 시 본인 것만)"""
        if user_id is None:
            return self.schedules
        return [s for s in self.schedules if s['user_id'] == user_id]

    def get_due_schedules(self) -> List[Dict]:
        """현재 실행해야 할 예약 목록 반환 (시간 도래 + 1분 이내)"""
        now = datetime.now()
        due = []
        for s in self.schedules:
            schedule_time = datetime.fromisoformat(s['time'])
            # 1분 이내 오차 허용
            if schedule_time <= now <= schedule_time + timedelta(minutes=1):
                due.append(s)
        return due

    def remove_executed(self, schedule_id: int):
        """실행 완료된 일회성 예약 제거"""
        self.schedules = [s for s in self.schedules if s['id'] != schedule_id or s['repeats']]
        self.save()


class Scheduler(commands.Cog):
    """예약 메시지 Cog"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.manager = ScheduleManager()
        self.check_schedules.start()  # 백그라운드 태스크 시작

    def cog_unload(self):
        """Cog 언로드 시 태스크 중지"""
        self.check_schedules.cancel()

    # ── 백그라운드 태스크: 1분마다 예약 확인 ────────────────────
    @tasks.loop(minutes=1)
    async def check_schedules(self):
        """1분마다 실행해야 할 예약 체크"""
        due = self.manager.get_due_schedules()
        for s in due:
            channel = self.bot.get_channel(s['channel_id'])
            if channel is None:
                print(f"⚠️ 채널을 찾을 수 없음: {s['channel_id']}")
                continue
            try:
                await channel.send(s['message'])
                print(f"📨 예약 메시지 전송: ID={s['id']} → {s['message'][:30]}")
            except Exception as e:
                print(f"❌ 예약 메시지 전송 실패: {e}")

            # 일회성이면 삭제
            if not s['repeats']:
                self.manager.remove_executed(s['id'])

    @check_schedules.before_loop
    async def before_check_schedules(self):
        """봇 준비될 때까지 대기"""
        await self.bot.wait_until_ready()

    # ── 슬래시 커맨드 ──────────────────────────────────────────
    schedule_group = app_commands.Group(name="schedule", description="예약 메시지 관리")

    @schedule_group.command(name="add", description="예약 메시지 추가")
    @app_commands.describe(
        time="시간 (YYYY-MM-DD HH:MM 또는 HH:MM)",
        message="전송할 메시지"
    )
    async def schedule_add(self, interaction: discord.Interaction, time: str, message: str):
        """예약 메시지 추가"""
        # 시간 파싱
        try:
            # YYYY-MM-DD HH:MM 형식
            if len(time) > 10:
                schedule_time = datetime.strptime(time, "%Y-%m-%d %H:%M")
            # HH:MM 형식 → 오늘 또는 내일
            else:
                now = datetime.now()
                t = datetime.strptime(time, "%H:%M").time()
                schedule_time = datetime.combine(now.date(), t)
                # 이미 지난 시간이면 내일로
                if schedule_time < now:
                    schedule_time += timedelta(days=1)
        except ValueError:
            await interaction.response.send_message(
                "❌ 시간 형식이 올바르지 않습니다.\n"
                "**형식:** `YYYY-MM-DD HH:MM` 또는 `HH:MM`\n"
                "**예시:** `2026-02-20 09:00` 또는 `07:00`",
                ephemeral=True
            )
            return

        # 과거 시간 체크
        if schedule_time < datetime.now():
            await interaction.response.send_message(
                "❌ 과거 시간으로는 예약할 수 없습니다.",
                ephemeral=True
            )
            return

        # 예약 추가
        s = self.manager.add(
            channel_id=interaction.channel_id,
            user_id=interaction.user.id,
            time=schedule_time,
            message=message
        )

        embed = discord.Embed(
            title="✅ 예약 메시지 추가 완료",
            color=discord.Color.green()
        )
        embed.add_field(name="예약 ID", value=f"`{s['id']}`", inline=True)
        embed.add_field(name="전송 시간", value=f"`{schedule_time.strftime('%Y-%m-%d %H:%M')}`", inline=True)
        embed.add_field(name="메시지", value=message, inline=False)
        embed.set_footer(text="삭제하려면 /schedule delete <ID>")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @schedule_group.command(name="list", description="예약 메시지 목록 확인")
    async def schedule_list(self, interaction: discord.Interaction):
        """예약 목록 확인"""
        schedules = self.manager.get_all(user_id=interaction.user.id)
        if not schedules:
            await interaction.response.send_message(
                "📭 등록된 예약 메시지가 없습니다.",
                ephemeral=True
            )
            return

        embed = discord.Embed(
            title=f"📅 내 예약 메시지 ({len(schedules)}개)",
            color=discord.Color.blue()
        )
        for s in schedules:
            time_str = datetime.fromisoformat(s['time']).strftime('%Y-%m-%d %H:%M')
            embed.add_field(
                name=f"ID: {s['id']} | {time_str}",
                value=f"{s['message'][:50]}{'...' if len(s['message']) > 50 else ''}",
                inline=False
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @schedule_group.command(name="delete", description="예약 메시지 삭제")
    @app_commands.describe(schedule_id="삭제할 예약 ID")
    async def schedule_delete(self, interaction: discord.Interaction, schedule_id: int):
        """예약 삭제"""
        deleted = self.manager.delete(schedule_id, interaction.user.id)
        if deleted is None:
            await interaction.response.send_message(
                "❌ 예약을 찾을 수 없거나 권한이 없습니다.",
                ephemeral=True
            )
            return

        embed = discord.Embed(
            title="🗑️ 예약 메시지 삭제 완료",
            description=f"**ID {schedule_id}** 예약이 삭제되었습니다.",
            color=discord.Color.orange()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    """Cog 설정 함수 (동적 로드용)"""
    await bot.add_cog(Scheduler(bot))
    print("✅ Scheduler Cog 동적 로드 완료")