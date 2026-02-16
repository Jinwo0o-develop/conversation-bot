"""
메모 관리 유틸리티 (v2.1 - 버그수정)

[수정 내역]
- BUG FIX: add_memory 에서 ID를 len(memories)+1 로 생성하던 방식 →
  삭제 후 재추가 시 기존 ID 와 충돌하는 문제 해소.
  max(existing_ids, default=0) + 1 방식으로 항상 고유 ID 보장.
"""
import json
import os
from typing import List, Dict, Optional
from datetime import datetime


class MemoManager:
    def __init__(self, memo_file: str = 'data/memories/peanut_memories.json'):
        self.memo_file = memo_file
        self.memories: List[Dict] = []
        self.load_memories()

    def load_memories(self) -> bool:
        try:
            if os.path.exists(self.memo_file):
                with open(self.memo_file, 'r', encoding='utf-8') as f:
                    self.memories = json.load(f).get('memories', [])
                print(f"✅ 메모리 파일 로드 완료: {len(self.memories)}개 메모")
            else:
                print(f"📝 새로운 메모리 파일 생성: {self.memo_file}")
                self.memories = []
                self.save_memories()
            return True
        except Exception as e:
            print(f"⚠️ 메모리 로드 오류: {e}")
            self.memories = []
            return False

    def save_memories(self) -> bool:
        try:
            os.makedirs(os.path.dirname(self.memo_file), exist_ok=True)
            with open(self.memo_file, 'w', encoding='utf-8') as f:
                json.dump(
                    {
                        'last_updated': datetime.now().isoformat(),
                        'total_count': len(self.memories),
                        'memories': self.memories,
                    },
                    f,
                    ensure_ascii=False,
                    indent=2
                )
            return True
        except Exception as e:
            print(f"❌ 메모리 저장 오류: {e}")
            return False

    def _next_id(self) -> int:
        """BUG FIX: 삭제 후 재추가 시 ID 중복 방지 - 현재 최대 ID + 1 반환"""
        if not self.memories:
            return 1
        return max(m['id'] for m in self.memories) + 1

    def add_memory(self, content: str, author: str = "관리자") -> Dict:
        memory = {
            'id': self._next_id(),   # BUG FIX: len+1 → max_id+1
            'content': content,
            'added_by': author,
            'timestamp': datetime.now().isoformat(),
            'date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        }
        self.memories.append(memory)
        self.save_memories()
        return memory

    def delete_memory(self, content: str) -> Optional[Dict]:
        for i, m in enumerate(self.memories):
            if m['content'] == content or content in m['content']:
                deleted = self.memories.pop(i)
                self.save_memories()
                return deleted
        return None

    def delete_memory_by_id(self, memory_id: int) -> Optional[Dict]:
        for i, m in enumerate(self.memories):
            if m['id'] == memory_id:
                deleted = self.memories.pop(i)
                self.save_memories()
                return deleted
        return None

    def search_memories(self, keyword: str) -> List[Dict]:
        return [m for m in self.memories if keyword.lower() in m['content'].lower()]

    def get_all_memories(self) -> List[Dict]:
        return self.memories.copy()

    def get_memory_count(self) -> int:
        return len(self.memories)

    def get_memories_as_text(self) -> str:
        if not self.memories:
            return "아직 저장된 취향이나 기억이 없습니다."
        return "=== 땅콩의 취향과 기억 ===\n" + "\n".join(
            f"- {m['content']}" for m in self.memories
        )

    def clear_all_memories(self) -> int:
        count = len(self.memories)
        self.memories = []
        self.save_memories()
        return count