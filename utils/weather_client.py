import aiohttp
from typing import Dict, Optional
from datetime import datetime

class WeatherClient:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "http://api.openweathermap.org/data/2.5"
    
    def interpret_wind_speed(self, speed_ms: float) -> str:
        if speed_ms < 1: return "바람 없음 😴"
        elif speed_ms < 3: return "약한 바람 🍃"
        elif speed_ms < 5: return "약간 불어요 🌬️"
        elif speed_ms < 8: return "좀 세요 💨"
        elif speed_ms < 11: return "세게 불어요 🌪️"
        elif speed_ms < 14: return "많이 세요! ⚠️"
        else: return "매우 강함! 🚨"
    
    def interpret_weather(self, weather_main: str, weather_desc: str) -> str:
        weather_map = {"Clear": "☀️ 맑음", "Clouds": "☁️ 구름", "Rain": "🌧️ 비", "Drizzle": "🌦️ 이슬비", "Thunderstorm": "⛈️ 천둥번개", "Snow": "❄️ 눈", "Mist": "🌫️ 안개", "Fog": "🌫️ 짙은 안개", "Haze": "🌁 실안개"}
        return weather_map.get(weather_main, f"🌈 {weather_main}")
    
    def interpret_clouds(self, clouds_percent: int) -> str:
        if clouds_percent < 20: return "맑음 ☀️"
        elif clouds_percent < 50: return "약간 흐림 ⛅"
        elif clouds_percent < 80: return "흐림 ☁️"
        else: return "많이 흐림 🌥️"
    
    async def get_current_weather(self, city: str, lang: str = "kr") -> Optional[Dict]:
        params = {"q": city, "appid": self.api_key, "units": "metric", "lang": lang}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.base_url}/weather", params=params) as response:
                    if response.status == 200:
                        return self._parse_current_weather(await response.json())
                    return None
        except Exception as e:
            print(f"❌ 날씨 API 오류: {e}")
            return None
    
    def _parse_current_weather(self, data: Dict) -> Dict:
        return {
            "city": data["name"], "country": data["sys"]["country"],
            "temp": round(data["main"]["temp"], 1), "feels_like": round(data["main"]["feels_like"], 1),
            "temp_min": round(data["main"]["temp_min"], 1), "temp_max": round(data["main"]["temp_max"], 1),
            "humidity": data["main"]["humidity"], "pressure": data["main"]["pressure"],
            "wind_speed": data["wind"]["speed"], "wind_speed_text": self.interpret_wind_speed(data["wind"]["speed"]),
            "clouds": data["clouds"]["all"], "clouds_text": self.interpret_clouds(data["clouds"]["all"]),
            "weather_main": data["weather"][0]["main"], "weather_desc": data["weather"][0]["description"],
            "weather_text": self.interpret_weather(data["weather"][0]["main"], data["weather"][0]["description"]),
            "rain": data.get("rain", {}).get("1h", 0), "snow": data.get("snow", {}).get("1h", 0),
            "timestamp": datetime.now()
        }