SERVER_ID = 1355771480402563152
CHANNEL_FREE = 1355771481195544729
CHANNEL_PROXY = 1376906087596294205
CHANNEL_BOT = 1436969729683095623
USER_ID = 723873904745250826

AVAILABLE_MODELS = [
    'gemini-3-pro-preview',
    'gemini-2.5-flash',
    'gemini-3-flash-preview',
    'gemini-2.5-flash-lite'
]

DEFAULT_MODEL = 'gemini-2.5-flash-lite'
DEFAULT_TEMPERATURE = 1.0
DEFAULT_TOP_P = 0.95
MAX_OUTPUT_TOKENS = 8192
MAX_HISTORY_LENGTH = 20
MESSAGE_COLLECT_DELAY = 3
SPLIT_PARTS = 3
SPLIT_MIN_DELAY = 0.3
SPLIT_MAX_DELAY = 0.5

PROMPT_FILE = 'data/prompts/Peanut_prompt_ultimate.txt'
DATASET_FILE = 'data/datasets/peanut_all_dataset.jsonl'
MEMO_FILE = 'data/memories/peanut_memories.json'

AVAILABLE_PROMPTS = [
    {'name': 'Ultimate', 'file': 'data/prompts/Peanut_prompt_ultimate.txt', 'description': '땅콩의 완전한 성격과 특성'},
    {'name': 'Optimize', 'file': 'data/prompts/Peanut_prompt_optimize.txt', 'description': '최적화된 프롬프트'}
]
DEFAULT_PROMPT_INDEX = 0
# 멀티 페르소나 프롬프트 빌더 전용 채널
CHANNEL_PERSONA = 1462774351740014633