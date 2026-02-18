"""
멀티 페르소나 프롬프트 빌더 Cog (v1.1)
"""
import discord
from discord.ext import commands
import asyncio
from typing import Dict, List
from google import genai
from google.genai.types import GenerateContentConfig
from config.settings import CHANNEL_PERSONA

EXTRACTION_SYSTEM_PROMPT = '# Role: 전문 프롬프트 엔지니어링 인터뷰어 (Extraction Module)\n당신의 목적은 사용자가 만들고자 하는 프롬프트의 핵심 정보를 추출하여 \'구조화된 데이터\'로 정리하는 것입니다.\n사용자가 한마디만 던지더라도, 아래의 필수 요소들을 인터뷰 형식의 질문을 통해 모두 파악해야 합니다.\n사용자는 프롬프트와 인공지능을 잘 모르는 초보자임을 명심하십시오.\n\n## 1. 인터뷰 원칙\n- 한 번에 너무 많은 질문을 하지 마십시오. (한 번에 1~2개씩 질문하여 대화 흐름 유지)\n- 사용자의 답변이 모호하면 "예를 들어 주실 수 있나요?"와 같이 구체화를 유도하십시오.\n- 전문 용어보다는 직관적이고 쉬운 단어를 사용하여 질문하십시오.\n\n## 2. 추출해야 할 필수 정보 (Extract Items)\n- **목적(Goal):** 이 프롬프트를 통해 최종적으로 얻고자 하는 결과물은 무엇인가?\n- **대상(Audience):** 이 결과물을 읽거나 사용할 사람은 누구인가?\n- **핵심 정보(Context):** AI가 알아야 할 배경지식이나 데이터는 무엇인가?\n- **제약 사항(Constraints):** 반드시 지켜야 할 규칙이나 절대 하지 말아야 할 행동은?\n- **예시(Few-shot):** 사용자가 생각하는 \'가장 이상적인 결과물\'의 샘플이 있는가?\n\n## 3. 작업 순서\n1. 사용자에게 어떤 프롬프트를 만들고 싶은지 가볍게 묻습니다.\n2. 사용자의 답변에 따라 부족한 정보를 채우기 위한 인터뷰를 진행합니다.\n3. 모든 정보가 수집되면, 아래의 [최종 출력 형식]에 맞춰 내용을 정리하여 코드블록형태로 제공합니다.\n\n## 4. [최종 출력 형식]\n(모든 정보 수집 완료 후, 사용자가 다음 Gem으로 이동할 수 있도록 이 형식을 제공하십시오.)\n\n---\n### [Extraction Result]\n- **Goal:** (내용 입력)\n- **Target Audience:** (내용 입력)\n- **Context/Topic:** (내용 입력)\n- **Constraints:** (내용 입력)\n- **Reference/Example:** (내용 입력)\n---\n위 내용을 복사하여 \'2번 Technique 결정 Gem\'에 붙여넣어 주세요.'

TECHNIQUE_SYSTEM_PROMPT  = "# Role: Prompt Engineering Strategist (Technique Module)\n\n## Context\n당신은 3단계 프롬프트 생성 파이프라인 중 2단계인 '전략 수립'을 담당합니다. 1단계(Extraction)에서 전달된 사용자 요구사항을 분석하여, AI 모델이 최상의 결과물을 낼 수 있는 기술적 방법론을 결정합니다.\n\n## Input Data\n사용자가 입력하는 1단계의 결과물(목적, 대상, 제약, 예시 등)을 기반으로 작동합니다.\n1단계에서 추출된 정보 중 AI의 내부 지식만으로 부족한 것이 있다면, 어떤 외부 데이터(RAG 파일 등)를 조회하여 보충할지 그 이유(Reasoning)를 전략에 포함시키십시오.\n\n## Task\n1. **기법(Technique) 결정**: 요구사항의 난이도와 유형에 따라 최적의 프롬프트 기법을 선택합니다.\n\xa0 \xa0- 예: 단계별 추론(CoT), 예시 제공(Few-Shot), 역할 부여(Persona), 역질문(Socratic),  문맥 분석(Contextual Analysis), 정보 엔트로피 극대화(Information Entropy Maximization), 의도적 도출/유도(Deliberate Derivation), 페르소나 가중치 설정(Persona Weighting), 스텝백 프롬프팅(Step-back Prompting) 등.\n      - 사용자가 사회적인 에티켓을 보지 않고 빠르게 결과를 제공하고 적은 설명을 원한다면 'Be concise and omit all conversational filler or etiquette.'을 적용하십시오.\n      - 논리적인 근거가 중요하다면 CoT 기법을, 비교 및 알고리즘 제작이라면 ToT 기법 등 상황에 맞게 적용하십시오.\n2. **어조(Tone & Style) 결정**: 최종 결과물이 타겟 독자에게 미칠 영향을 고려하여 말투와 스타일을 정의합니다.\n3. **논리적 근거 제시**: 왜 이 기법과 어조를 선택했는지 사용자에게 짧고 명확하게 설명합니다.\n4. ART 기반 도구 분석(Tool Reasoning):\n\n - 과업 해결을 위해 LLM의 내부 지식 외에 외부 데이터가 필요한지 판단합니다.\n - Search: 최신 라이브러리 업데이트나 스펙 확인이 필요한가?\n - Code Interpreter: 복잡한 알고리즘 검증이나 수학적 계산이 필요한가?\n - RAG (Knowledge Retrieval): 사용자에게서(배경,추가로 필요한 자료 등) 특정 레퍼런스를 참조해야 하는가?\n\n선택된 도구가 있다면, 왜 해당 도구가 필요한지 논리적 근거(Reasoning)를 기술하십시오.\n## Output Format\n---\n### 🛠 선택된 프롬프트 전략\n\n**1. 적용 기법 (Techniques)**\n- [선택된 기법 명칭]\n- [선택된 기법 명칭]\n\n**2. 페르소나 및 어조 (Persona & Tone)**\n- [설정된 역할 및 말투 스타일]\n\n--\n**[Next Step]**\n위 전략이 확정되었다면, 이 내용을 복사하여 '3번 PromptGenerator' Gem에 입력해 주세요."

GENERATOR_SYSTEM_PROMPT  = '# Role: 프롬프트 엔지니어링 마스터 (PromptGenerator)\n당신은 1번(Extraction)과 2번(Technique) 모듈에서 도출된 데이터를 바탕으로, 최종적인 고성능 프롬프트를 설계하는 전문가입니다. 단순히 정보를 나열하는 것이 아니라, AI의 성능을 극대화할 수 있는 구조적이고 논리적인 프롬프트를 생성합니다.\n\n## Input Data\n사용자로부터 다음 정보를 입력받습니다:\n1. Extraction 모듈 결과 (목적, 대상, 제약, 예시 등)\n2. Technique 결정 결과 (선택된 기법 및 어조, 이유)\n\n## Workflow & Guidelines\n### 1. 정보 분석 및 심화 질문\n- 입력된 정보를 분석하여 프롬프트의 완성도를 높이기 위해 \'더 구체화가 필요한 부분\'이 있다면 먼저 짧게 질문합니다. (예: 구체적인 출력 포맷, 데이터의 양, 예외 상황 처리 등)\n최종 프롬프트에는 AI가 정보를 찾을 때 사용할 형식을 포함하라. 예: [도구: RAG] - 검색 키워드: {핵심키워드}. 이를 통해 AI가 근거를 명시적으로 찾도록 유도하십시오.\n\n### 2. 구조적 프롬프트 생성\n최종 결과물은 반드시 다음 구조를 포함해야 합니다:\n- **Persona (역할, Tone & Style 포함):** 해당 과업을 수행하기 가장 적합한 전문가 설정 \n- **Task (과업):** 수행해야 할 구체적인 작업 내용\n- **Context(맥락):** 프롬프트에 적용될 사용자의 상황\n- **Constraints(제약사항):** 1번 모듈에서 정의된 제약 사항 반영\n- **Technique(맞춤형 기법제공):** AI가 사고의 흐름을 가질 수 있도록 작업 순서 규정 (2번 모듈에서 제공된 기법을 맞춤형으로 반영)\n- **Output Format (출력 형식):** 사용자가 원하는 형태(Markdown, JSON, Table, 출력 구조 등) 지정\n- **Goal(목표):** 사용자의 요구에 맞는 목표 제공\n\n### 3. AI의 능동적 제안 (Critical Feature)\n- **도메인 특화 제약 조건 추천:** 사용자가 직접 언급하지 않았더라도, 해당 도메인(예: 법률, 코딩, 마케팅, 소설 등)에서 품질을 높이기 위해 반드시 지켜야 할 제약 조건을 최소 2~3가지 AI가 스스로 판단하여 프롬프트에 포함시킵니다.\n\n## Output Style\n- 생성된 프롬프트는 사용자가 바로 복사해서 사용할 수 있도록 **코드 블록** 내에 제공하십시오.\n- 프롬프트 하단에는 "이 프롬프트에 포함된 핵심 전략"을 간략히 설명합니다.'

SESSION_GREETING = {
    "extraction": "안녕하세요! 프롬프트 요구사항을 함께 정리해 드리는 도우미입니다 😊\n\n어떤 목적으로 프롬프트를 만들고 싶으신가요? 아무리 간단한 아이디어라도 괜찮습니다. 편하게 말씀해 주세요!",
    "technique":  "안녕하세요! 기법 적용 단계입니다 🛠\n\n📋 **1단계(요구사항 추출) 결과**를 이 채널에 붙여넣어 주시면, 최적의 프롬프트 기법을 분석해 드리겠습니다.",
    "generator":  "안녕하세요! 프롬프트 생성 단계입니다 ✨\n\n📋 **1단계(요구사항 추출) 결과**와 🛠 **2단계(기법 적용) 결과**를 모두 붙여넣어 주시면 최종 프롬프트를 생성해 드리겠습니다.",
}

MODULE_INFO = {
    "extraction": ("📋 요구사항 추출", discord.Color.blue()),
    "technique":  ("🛠 기법 적용",    discord.Color.orange()),
    "generator":  ("✨ 프롬프트 생성", discord.Color.green()),
}


class PersonaSession:
    """메인 GeminiClient와 완전히 분리된 독립 Gemini 세션"""
    def __init__(self, api_key: str, module: str, system_prompt: str):
        self.client        = genai.Client(api_key=api_key)
        self.module        = module
        self.system_prompt = system_prompt
        self.histories: Dict[int, List[dict]] = {}

    def _config(self) -> GenerateContentConfig:
        return GenerateContentConfig(
            temperature=0.7,
            top_p=0.95,
            max_output_tokens=2048,
            system_instruction=self.system_prompt
        )

    def get_history(self, user_id: int) -> List[dict]:
        return self.histories.setdefault(user_id, [])

    def clear_history(self, user_id: int):
        self.histories[user_id] = []

    def generate(self, user_id: int, text: str) -> str:
        history  = self.get_history(user_id)
        messages = history + [{"role": "user", "parts": [{"text": text}]}]
        response = self.client.models.generate_content(
            model="gemini-2.5-flash",
            contents=messages,
            config=self._config()
        )
        reply = response.text
        history.append({"role": "user",  "parts": [{"text": text}]})
        history.append({"role": "model", "parts": [{"text": reply}]})
        if len(history) > 80:
            self.histories[user_id] = history[-80:]
        return reply


class PersonaHandler(commands.Cog):
    """멀티 페르소나 프롬프트 빌더 Cog"""

    def __init__(self, bot: commands.Bot, api_key: str):
        self.bot = bot
        self.sessions: Dict[str, PersonaSession] = {
            "extraction": PersonaSession(api_key, "extraction", EXTRACTION_SYSTEM_PROMPT),
            "technique":  PersonaSession(api_key, "technique",  TECHNIQUE_SYSTEM_PROMPT),
            "generator":  PersonaSession(api_key, "generator",  GENERATOR_SYSTEM_PROMPT),
        }
        self._active: Dict[int, str] = {}

    async def start_session(self, interaction: discord.Interaction, module: str):
        user_id     = interaction.user.id
        name, color = MODULE_INFO[module]
        emoji       = name.split()[0]

        self.sessions[module].clear_history(user_id)
        self._active[user_id] = module

        channel = self.bot.get_channel(CHANNEL_PERSONA)
        if channel is None:
            await interaction.response.send_message(
                f"❌ 페르소나 채널을 찾을 수 없습니다. (ID: {CHANNEL_PERSONA})",
                ephemeral=True
            )
            return

        await interaction.response.send_message(
            f"{emoji} **{name}** 세션을 시작합니다.\n➡️ <#{CHANNEL_PERSONA}> 채널로 이동해 주세요!",
            ephemeral=True
        )

        embed = discord.Embed(
            title=f"{emoji} {name} 세션 시작",
            description=(
                f"<@{user_id}> 님의 **{name}** 세션이 시작되었습니다.\n"
                f"세션을 종료하려면 `!persona stop` 을 입력하세요."
            ),
            color=color
        )
        embed.set_footer(text="이 세션은 메인 봇 대화와 완전히 분리됩니다.")
        await channel.send(embed=embed)
        await channel.send(f"{emoji} {SESSION_GREETING[module]}")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        if message.channel.id != CHANNEL_PERSONA:
            return
        if message.content.startswith(("/", "!", "\\")):
            return

        user_id = message.author.id
        module  = self._active.get(user_id)

        if module is None:
            await message.channel.send(
                f"<@{user_id}> `/prompt` 명령어에서 버튼을 눌러 세션을 먼저 시작해 주세요.\n"
                f"📋 요구사항 추출 → 🛠 기법 적용 → ✨ 프롬프트 생성 순서로 진행하시면 됩니다.",
                delete_after=15
            )
            return

        session = self.sessions[module]
        emoji   = MODULE_INFO[module][0].split()[0]

        async with message.channel.typing():
            try:
                reply = await asyncio.to_thread(session.generate, user_id, message.content)
                if len(reply) > 1900:
                    for i in range(0, len(reply), 1900):
                        await message.channel.send(f"{emoji} {reply[i:i+1900]}")
                else:
                    await message.channel.send(f"{emoji} {reply}")
            except Exception as e:
                print(f"❌ PersonaSession 오류: {e}")
                await message.channel.send("⚠️ 응답 생성 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.")

    @commands.command(name="persona")
    async def persona_cmd(self, ctx: commands.Context, action: str = "stop"):
        if action != "stop":
            return
        user_id = ctx.author.id
        module  = self._active.pop(user_id, None)
        if module is None:
            await ctx.send("현재 활성 페르소나 세션이 없습니다.", delete_after=5)
            return
        self.sessions[module].clear_history(user_id)
        name, color = MODULE_INFO[module]
        embed = discord.Embed(
            title=f"⏹️ {name} 세션 종료",
            description=f"<@{user_id}> 님의 **{name}** 세션이 종료되고 히스토리가 초기화되었습니다.",
            color=discord.Color.greyple()
        )
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    if not hasattr(bot, "google_api_key"):
        raise RuntimeError("bot.google_api_key가 설정되지 않았습니다.")
    await bot.add_cog(PersonaHandler(bot, bot.google_api_key))
    print("✅ PersonaHandler Cog 동적 로드 완료")