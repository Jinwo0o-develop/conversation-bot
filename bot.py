"""
Discord 공책봇 - 메인 파일 (v3.2 - 최적화)
"""
import discord
from discord.ext import commands
import os
from dotenv import load_dotenv

from config.settings import (
    CHANNEL_BOT, DEFAULT_MODEL, DEFAULT_TEMPERATURE, DEFAULT_TOP_P,
    MAX_OUTPUT_TOKENS, PROMPT_FILE, DATASET_FILE, MEMO_FILE
)
from utils.gemini_client import GeminiClient
from utils.memo_manager import MemoManager
from cogs.chat_handler import ChatHandler
from cogs.commands import BotCommands
from cogs.slash_commands import SlashCommands


class PeanutBot:
    """공책봇 메인 클래스"""
    
    def __init__(self):
        """봇 초기화"""
        load_dotenv()
        
        self.discord_token = os.getenv('DISCORD_BOT_TOKEN')
        self.google_api_key = os.getenv('GOOGLE_API_KEY')
        
        if not self.discord_token or not self.google_api_key:
            raise ValueError(
                "❌ .env 파일에 API 키가 설정되지 않았습니다!\n"
                "DISCORD_BOT_TOKEN과 GOOGLE_API_KEY를 확인하세요."
            )
        
        intents = discord.Intents.default()
        intents.message_content = True
        intents.messages = True
        
        self.bot = commands.Bot(
            command_prefix='/',
            intents=intents,
            help_command=None
        )
        
        self.gemini_client = GeminiClient(
            api_key=self.google_api_key,
            model_name=DEFAULT_MODEL,
            temperature=DEFAULT_TEMPERATURE,
            top_p=DEFAULT_TOP_P,
            max_output_tokens=MAX_OUTPUT_TOKENS
        )
        
        self.memo_manager = MemoManager(memo_file=MEMO_FILE)
        
        self.chat_handler = None
        self.bot_commands = None
        self.slash_commands = None
        
        self.setup_events()
    
    def setup_events(self):
        """봇 이벤트 핸들러 설정"""
        
        @self.bot.event
        async def on_ready():
            """봇 준비 완료 이벤트"""
            print("=" * 50)
            print(f"✅ {self.bot.user} 봇이 준비되었습니다!")
            print(f"📌 현재 모델: {self.gemini_client.model_name}")
            print(f"🌡️ Temperature: {self.gemini_client.temperature}")
            print(f"🎯 Top-p: {self.gemini_client.top_p}")
            print("=" * 50)
            
            self.gemini_client.load_system_prompt(PROMPT_FILE)
            self.load_dataset()
            await self.setup_cogs()
            
            print("✅ 모든 초기화 완료!")
            print("=" * 50)
        
        @self.bot.event
        async def on_command_error(ctx, error):
            """명령어 오류 처리"""
            if isinstance(error, commands.CommandNotFound):
                return
            elif isinstance(error, commands.MissingRequiredArgument):
                await ctx.send(f"❌ 필수 인자가 누락되었습니다: `{error.param.name}`")
            elif isinstance(error, commands.BadArgument):
                await ctx.send(f"❌ 잘못된 인자입니다: {error}")
            elif isinstance(error, commands.MissingPermissions):
                await ctx.send("❌ 이 명령어를 사용할 권한이 없습니다.")
            else:
                print(f"❌ 명령어 오류: {error}")
                await ctx.send(f"❌ 오류가 발생했습니다: {error}")
    
    async def setup_cogs(self):
        """Cogs 설정 및 추가"""
        self.chat_handler = ChatHandler(self.bot, self.gemini_client)
        await self.bot.add_cog(self.chat_handler)
        print("✅ ChatHandler Cog 로드 완료")
        
        self.bot_commands = BotCommands(
            self.bot,
            self.gemini_client,
            self.chat_handler,
            self.memo_manager
        )
        await self.bot.add_cog(self.bot_commands)
        print("✅ BotCommands Cog 로드 완료")
        
        self.slash_commands = SlashCommands(
            self.bot,
            self.gemini_client,
            self.chat_handler,
            self.memo_manager
        )
        await self.bot.add_cog(self.slash_commands)
        print("✅ SlashCommands Cog 로드 완료")
        
        try:
            # 기존 등록된 명령어 전체 삭제 후 재동기화
            self.bot.tree.clear_commands(guild=None)
            synced = await self.bot.tree.sync()
            print(f"✅ 슬래시 커맨드 동기화 완료: {len(synced)}개 명령어")
        except Exception as e:
            print(f"⚠️ 슬래시 커맨드 동기화 실패: {e}")
        
        memory_text = self.memo_manager.get_memories_as_text()
        self.gemini_client.update_memories(memory_text)
        print(f"✅ 메모리 로드 완료: {self.memo_manager.get_memory_count()}개")
    
    def load_dataset(self):
        """데이터셋 파일 확인"""
        try:
            with open(DATASET_FILE, 'r', encoding='utf-8') as f:
                f.readline()
            print(f"✅ 데이터셋 파일 확인 완료: {DATASET_FILE}")
        except FileNotFoundError:
            print(f"⚠️ {DATASET_FILE} 파일을 찾을 수 없습니다.")
        except Exception as e:
            print(f"⚠️ 데이터셋 로드 중 오류: {e}")
    
    def run(self):
        """봇 실행"""
        try:
            print("🚀 봇을 시작합니다...")
            self.bot.run(self.discord_token)
        except KeyboardInterrupt:
            print("\n⏹️ 봇을 종료합니다...")
        except Exception as e:
            print(f"❌ 봇 실행 중 오류: {e}")


def main():
    """메인 함수"""
    try:
        bot = PeanutBot()
        bot.run()
    except ValueError as e:
        print(str(e))
    except Exception as e:
        print(f"❌ 초기화 중 오류 발생: {e}")


if __name__ == '__main__':
    main()