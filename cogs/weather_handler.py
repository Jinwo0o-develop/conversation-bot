"""
날씨 Cog (v1.0)

OpenWeatherMap API 기반 날씨 조회 및 자동 알림 기능

[기능]
- /weather <도시>           — 현재 날씨 즉시 조회
- /weather forecast <도시>  — 오늘 하루 예보 (3시간 간격)
- /weather register <도시>  — 매일 07시 자동 알림 지역 등록
- /weather unregister       — 자동 알림 해제
- /weather list             — 등록된 지역 목록

[자동 알림]
- 매일 07:00에 등록된 지역의 하루 예보를 표 형식으로 전송
- 비 시작 또는 급격한 기온 변화(±5도) 구간에서 추가 행 삽입

[저장 구조]
data/weather_subscriptions.json:
{
  "subscriptions": [
    {
      "user_id": 123456,
      "channel_id": 789012,
      "city": "Suwon",
      "created_at": "2026-02-19T10:00:00"
    }
  ]
}
"""
import discord
from discord import app_commands
from discord.ext import commands, tasks
from datetime import datetime, time as dt_time, timedelta
from typing import List, Dict, Optional
import json
import os

from utils.weather_client import WeatherClient

SUBSCRIPTION_FILE = "data/weather_subscriptions.json"


class WeatherSubscriptionManager:
    """날씨 구독 관리 (JSON 기반 영속화)"""

    def __init__(self, filepath: str = SUBSCRIPTION_FILE):
        self.filepath = filepath
        self.subscriptions: List[Dict] = []
        self.load()

    def load(self):
        os.makedirs(os.path.dirname(self.filepath), exist_ok=True)
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.subscriptions = data.get("subscriptions", [])
                print(f"✅ 날씨 구독 로드: {len(self.subscriptions)}개")
            except Exception as e:
                print(f"⚠️ 날씨 구독 파일 로드 실패: {e}")
                self.subscriptions = []
        else:
            self.subscriptions = []

    def save(self):
        try:
            with open(self.filepath, 'w', encoding='utf-8') as f:
                json.dump({"subscriptions": self.subscriptions}, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"❌ 날씨 구독 저장 실패: {e}")

    def add(self, user_id: int, city: str) -> Dict:
        """구독 추가 (중복 시 덮어쓰기)"""
        # 기존 구독 제거 (1인 1지역)
        self.subscriptions = [s for s in self.subscriptions if s['user_id'] != user_id]
        sub = {
            "user_id": user_id,
            "city": city,
            "created_at": datetime.now().isoformat()
        }
        self.subscriptions.append(sub)
        self.save()
        return sub

    def remove(self, user_id: int) -> bool:
        """구독 해제"""
        before = len(self.subscriptions)
        self.subscriptions = [s for s in self.subscriptions if s['user_id'] != user_id]
        if len(self.subscriptions) < before:
            self.save()
            return True
        return False

    def get_all(self) -> List[Dict]:
        """전체 구독 목록"""
        return self.subscriptions

    def get_by_user(self, user_id: int) -> Optional[Dict]:
        """특정 유저의 구독 조회"""
        for s in self.subscriptions:
            if s['user_id'] == user_id:
                return s
        return None


class WeatherHandler(commands.Cog):
    """날씨 조회 및 자동 알림 Cog"""

    def __init__(self, bot: commands.Bot, api_key: str):
        self.bot = bot
        self.weather_client = WeatherClient(api_key)
        self.subscription_manager = WeatherSubscriptionManager()
        self.daily_weather_alert.start()

    def cog_unload(self):
        self.daily_weather_alert.cancel()

    # ── 백그라운드 태스크: 매일 07:00 날씨 알림 ──────────────────
    @tasks.loop(time=dt_time(hour=7, minute=0))
    async def daily_weather_alert(self):
        """매일 07:00에 구독자들에게 DM으로 날씨 알림"""
        subscriptions = self.subscription_manager.get_all()
        if not subscriptions:
            return

        for sub in subscriptions:
            user = self.bot.get_user(sub['user_id'])
            if user is None:
                # 캐시에 없으면 fetch 시도
                try:
                    user = await self.bot.fetch_user(sub['user_id'])
                except:
                    print(f"⚠️ 사용자를 찾을 수 없음: {sub['user_id']}")
                    continue

            city = sub['city']
            forecasts = await self.weather_client.get_forecast(city)
            if forecasts is None:
                continue

            # 오늘 하루치만 필터링 (24시간 이내)
            today = datetime.now().date()
            today_forecasts = [f for f in forecasts if f['dt'].date() == today]

            if not today_forecasts:
                continue

            # 표 생성 (스마트 행 추가 포함)
            table_text = self._build_forecast_table(today_forecasts, city)
            embed = discord.Embed(
                title=f"🌤️ 오늘의 날씨 - {city}",
                description=f"```\n{table_text}\n```",
                color=discord.Color.blue(),
                timestamp=datetime.now()
            )
            embed.set_footer(text="매일 07:00 자동 알림 | 해제하려면 /weather unregister")

            try:
                await user.send(embed=embed)
                print(f"📨 날씨 알림 전송 (DM): {city} → {user.name}")
            except discord.Forbidden:
                print(f"⚠️ DM 전송 실패 (차단됨): {user.name}")
            except Exception as e:
                print(f"❌ 날씨 알림 전송 실패: {e}")

    @daily_weather_alert.before_loop
    async def before_daily_weather_alert(self):
        await self.bot.wait_until_ready()

    def _build_forecast_table(self, forecasts: List[Dict], city: str) -> str:
        """
        예보 데이터를 표 형식으로 변환
        - 기본: 3시간 간격 출력
        - 스마트 추가: 비 시작 또는 급격한 기온 변화(±5도) 시 추가 행
        """
        if not forecasts:
            return "예보 데이터 없음"

        lines = []
        lines.append("시간  | 날씨       | 기온  | 강수 | 바람")
        lines.append("------|-----------|------|------|------")

        prev_temp = None
        prev_rain = False

        for f in forecasts:
            time_str = f['dt'].strftime('%H:%M')
            weather = f['weather_text'][:6]
            temp = f['temp']
            rain = f['rain_3h'] > 0
            wind = f['wind_speed_text'][:6]
            pop = int(f['pop'])

            # 비 시작 감지
            if rain and not prev_rain:
                lines.append(f"{time_str} | ⚠️ 비 시작!  | {temp}°C | {pop}% | {wind}")
            # 급격한 기온 변화 (±5도)
            elif prev_temp is not None and abs(temp - prev_temp) >= 5:
                change = "↑" if temp > prev_temp else "↓"
                lines.append(f"{time_str} | {change} 급변화! | {temp}°C | {pop}% | {wind}")
            # 일반 출력
            else:
                lines.append(f"{time_str} | {weather:9s} | {temp}°C | {pop}% | {wind}")

            prev_temp = temp
            prev_rain = rain

        return "\n".join(lines)

    # ── 슬래시 커맨드 ──────────────────────────────────────────
    weather_group = app_commands.Group(name="weather", description="날씨 조회 및 알림")

    @weather_group.command(name="now", description="현재 날씨 조회")
    @app_commands.describe(city="도시 이름 (예: Suwon, Seoul)")
    async def weather_now(self, interaction: discord.Interaction, city: str):
        """현재 날씨 조회"""
        await interaction.response.defer(ephemeral=True)
        weather = await self.weather_client.get_current_weather(city)

        if weather is None:
            await interaction.followup.send(
                f"❌ '{city}' 날씨 정보를 가져올 수 없습니다.",
                ephemeral=True
            )
            return

        embed = discord.Embed(
            title=f"🌤️ 현재 날씨 - {weather['city']}, {weather['country']}",
            color=discord.Color.blue(),
            timestamp=weather['timestamp']
        )
        embed.add_field(name="날씨", value=weather['weather_text'], inline=True)
        embed.add_field(name="기온", value=f"{weather['temp']}°C (체감 {weather['feels_like']}°C)", inline=True)
        embed.add_field(name="습도", value=f"{weather['humidity']}%", inline=True)
        embed.add_field(name="바람", value=weather['wind_speed_text'], inline=True)
        embed.add_field(name="구름", value=weather['clouds_text'], inline=True)
        await interaction.followup.send(embed=embed, ephemeral=True)

    @weather_group.command(name="forecast", description="오늘 하루 예보 (3시간 간격)")
    @app_commands.describe(city="도시 이름 (예: Suwon, Seoul)")
    async def weather_forecast(self, interaction: discord.Interaction, city: str):
        """오늘 하루 예보"""
        await interaction.response.defer(ephemeral=True)
        forecasts = await self.weather_client.get_forecast(city)

        if forecasts is None:
            await interaction.followup.send(
                f"❌ '{city}' 예보 정보를 가져올 수 없습니다.",
                ephemeral=True
            )
            return

        # 오늘 하루치만 필터링
        today = datetime.now().date()
        today_forecasts = [f for f in forecasts if f['dt'].date() == today]

        if not today_forecasts:
            await interaction.followup.send(
                f"⚠️ '{city}'의 오늘 예보가 없습니다.",
                ephemeral=True
            )
            return

        table_text = self._build_forecast_table(today_forecasts, city)
        embed = discord.Embed(
            title=f"🌤️ 오늘의 날씨 - {city}",
            description=f"```\n{table_text}\n```",
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @weather_group.command(name="register", description="매일 07시 날씨 알림 등록 (DM 전송)")
    @app_commands.describe(city="알림 받을 도시 이름")
    async def weather_register(self, interaction: discord.Interaction, city: str):
        """날씨 알림 등록"""
        await interaction.response.defer(ephemeral=True)
        
        # 도시 유효성 검증 + 예보 조회
        forecasts = await self.weather_client.get_forecast(city)
        if forecasts is None:
            await interaction.followup.send(
                f"❌ '{city}'는 유효하지 않은 도시명이거나 예보를 가져올 수 없습니다.",
                ephemeral=True
            )
            return

        # 구독 등록
        sub = self.subscription_manager.add(
            user_id=interaction.user.id,
            city=city
        )

        # 등록 완료 메시지 (ephemeral)
        embed = discord.Embed(
            title="✅ 날씨 알림 등록 완료",
            description=(
                f"**도시:** {city}\n"
                f"**알림 시간:** 매일 07:00\n"
                f"**전송 방식:** 개인 메시지(DM)\n\n"
                f"지금 바로 첫 예보를 DM으로 보내드립니다!"
            ),
            color=discord.Color.green()
        )
        embed.set_footer(text="해제하려면 /weather unregister")
        await interaction.followup.send(embed=embed, ephemeral=True)

        # 오늘 하루치 예보 필터링
        today = datetime.now().date()
        today_forecasts = [f for f in forecasts if f['dt'].date() == today]

        if not today_forecasts:
            # 오늘 예보 없으면 내일 첫 예보
            tomorrow = datetime.now().date() + timedelta(days=1)
            today_forecasts = [f for f in forecasts if f['dt'].date() == tomorrow][:8]

        # DM 전송
        table_text = self._build_forecast_table(today_forecasts, city)
        forecast_embed = discord.Embed(
            title=f"🌤️ 오늘의 날씨 - {city}",
            description=f"```\n{table_text}\n```",
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )
        forecast_embed.set_footer(text="매일 07:00 자동 알림 | 해제하려면 /weather unregister")

        try:
            await interaction.user.send(embed=forecast_embed)
            print(f"📨 날씨 등록 즉시 전송 (DM): {city} → {interaction.user.name}")
        except discord.Forbidden:
            # DM 차단된 경우 ephemeral 채널 메시지로 전송
            await interaction.followup.send(
                f"⚠️ DM 전송이 차단되어 있습니다. 아래에서 확인하세요:\n",
                embed=forecast_embed,
                ephemeral=True
            )
            print(f"⚠️ DM 차단 (채널 대체 전송): {interaction.user.name}")
        except Exception as e:
            print(f"❌ 예보 전송 실패: {e}")

    @weather_group.command(name="unregister", description="날씨 알림 해제")
    async def weather_unregister(self, interaction: discord.Interaction):
        """날씨 알림 해제"""
        success = self.subscription_manager.remove(interaction.user.id)
        if success:
            await interaction.response.send_message(
                "🔕 날씨 알림이 해제되었습니다.",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                "⚠️ 등록된 날씨 알림이 없습니다.",
                ephemeral=True
            )

    @weather_group.command(name="list", description="등록된 날씨 알림 목록")
    async def weather_list(self, interaction: discord.Interaction):
        """날씨 알림 목록"""
        sub = self.subscription_manager.get_by_user(interaction.user.id)
        if sub is None:
            await interaction.response.send_message(
                "📭 등록된 날씨 알림이 없습니다.\n`/weather register <도시>` 로 등록하세요.",
                ephemeral=True
            )
            return

        embed = discord.Embed(
            title="📋 내 날씨 알림",
            color=discord.Color.blue()
        )
        embed.add_field(name="도시", value=sub['city'], inline=True)
        embed.add_field(name="전송 방식", value="개인 메시지(DM)", inline=True)
        embed.add_field(name="등록일", value=sub['created_at'][:10], inline=True)
        embed.set_footer(text="매일 07:00 자동 전송")
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    """Cog 설정 함수 (동적 로드용)"""
    if not hasattr(bot, 'weather_api_key'):
        raise RuntimeError("bot.weather_api_key가 설정되지 않았습니다.")
    await bot.add_cog(WeatherHandler(bot, bot.weather_api_key))
    print("✅ WeatherHandler Cog 동적 로드 완료")