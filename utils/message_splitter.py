import re
from typing import List

class MessageSplitter:
    @staticmethod
    def split_by_lines(text: str, parts: int = 3) -> List[str]:
        text = text.replace('\\n', '\n')
        lines = text.split('\n')
        if len(lines) <= parts:
            return [l for l in lines if l.strip()]
        
        lines_per_part = len(lines) // parts
        remainder = len(lines) % parts
        chunks, start = [], 0
        
        for i in range(parts):
            end = start + lines_per_part + (1 if i < remainder else 0)
            chunk = '\n'.join(lines[start:end]).strip()
            if chunk: chunks.append(chunk)
            start = end
        return chunks
    
    @staticmethod
    def split_by_sentences(text: str, parts: int = 3) -> List[str]:
        text = text.replace('\\n', '\n')
        sentences = re.split(r'([.!?\n])', text)
        combined = []
        for i in range(0, len(sentences) - 1, 2):
            if i + 1 < len(sentences):
                c = sentences[i] + sentences[i+1]
                if c.strip(): combined.append(c.strip())
        if len(sentences) % 2 == 1 and sentences[-1].strip():
            combined.append(sentences[-1].strip())
        if not combined: return [text]
        if len(combined) <= parts: return combined
        
        spp = len(combined) // parts
        rem = len(combined) % parts
        chunks, start = [], 0
        for i in range(parts):
            end = start + spp + (1 if i < rem else 0)
            chunk = ' '.join(combined[start:end]).strip()
            if chunk: chunks.append(chunk)
            start = end
        return chunks
    
    @staticmethod
    def smart_split(text: str, parts: int = 3) -> List[str]:
        if text.count('\n') >= parts or text.count('\\n') >= parts:
            return MessageSplitter.split_by_lines(text, parts)
        return MessageSplitter.split_by_sentences(text, parts)