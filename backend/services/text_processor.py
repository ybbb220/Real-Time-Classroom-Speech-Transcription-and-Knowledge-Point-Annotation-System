import re
from dataclasses import dataclass, field

MIN_CHARS = 10          # 少于该字数且无句末标点的句子暂不发出
MAX_CHARS = 30          # 超过该字数尝试在逗号/分号处切分
MERGE_MIN_CHARS = 6     # 少于此字数的碎片强制与前句合并

# 句末标点
SENTENCE_END = re.compile(r"[。！？!?…—]$")
# 句中可切分标点
CLAUSE_SEP = re.compile(r"[,，;；]")
# 话题起始词
TOPIC_START = re.compile(
    r"^(接下来|下面|首先|然后|其次|最后|另外|此外|还有|"
    r"我们来看|接下来看|接下来讲|下面讲|下面来看|"
    r"第[一二三四五六七八九十\d]+[章节课]|"
    r"总结|小结|复习|预习|布置|考试|测验|作业|思考|讨论|提问)"
)


@dataclass
class ProcessedSentence:

    text: str
    source_indices: list[int] = field(default_factory=list)


class SentenceProcessor:

    def __init__(
        self,
        min_chars: int = MIN_CHARS,
        max_chars: int = MAX_CHARS,
        merge_min_chars: int = MERGE_MIN_CHARS,
    ):
        self.min_chars = min_chars
        self.max_chars = max_chars
        self.merge_min_chars = merge_min_chars
        self._buf: str = ""           # 短句缓冲
        self._buf_indices: list[int] = []  # 缓冲对应的原始索引
        self._index: int = 0          # 当前原始句子索引

    def feed(self, raw: str) -> str | None:
        # 喂入一个原始句子，返回处理后可发出的句子
        text = raw.strip()
        if not text:
            self._index += 1
            return None

        self._index += 1
        idx = self._index - 1

        # 有话题起始词
        if TOPIC_START.match(text):
            flushed = self._flush_buf()
            # 对当前句做常规处理
            processed = self._process_single(text, source_idx=idx)
            if flushed:
                return flushed.text + processed.text if processed else flushed.text
            return processed.text if processed else None

        # 当前句很短且无句末标点
        if len(text) < self.min_chars and not SENTENCE_END.search(text):
            if self._buf:
                # 已有缓冲则合并后重新判断
                combined = self._buf + text
                self._buf = ""
                self._buf_indices.append(idx)
                merged_idx = self._buf_indices[:]
                self._buf_indices = []
                # 合并后仍短则继续缓冲
                if len(combined) < self.min_chars and not SENTENCE_END.search(combined):
                    self._buf = combined
                    self._buf_indices = merged_idx
                    return None
                return self._process_single(combined, source_indices=merged_idx).text
            else:
                self._buf = text
                self._buf_indices = [idx]
                return None

        # 有缓冲且有当前句则合并发出
        if self._buf:
            combined = self._buf + text
            combined_indices = self._buf_indices + [idx]
            self._buf = ""
            self._buf_indices = []
            return self._process_single(combined, source_indices=combined_indices).text

        return self._process_single(text, source_idx=idx).text

    def flush(self) -> str | None:
        # 强制发出缓冲中剩余的句子
        return self._flush_buf()

    def _flush_buf(self) -> str | None:
        if not self._buf:
            return None
        text = self._buf
        indices = list(self._buf_indices)
        self._buf = ""
        self._buf_indices = []
        return self._process_single(text, source_indices=indices).text

    def _process_single(
        self,
        text: str,
        source_idx: int = -1,
        source_indices: list[int] = None,
    ) -> ProcessedSentence:
        if source_indices is None:
            source_indices = [source_idx] if source_idx >= 0 else []

        # 长句切分
        if len(text) > self.max_chars:
            parts = self._split_long(text)
            if len(parts) > 1:
                result = parts[0]
                remainder = "".join(parts[1:])
                if remainder.strip():
                    self._buf = remainder + (self._buf or "")
                    self._buf_indices = source_indices + (self._buf_indices or [])
                return ProcessedSentence(
                    text=self._normalize(result), source_indices=source_indices
                )

        return ProcessedSentence(
            text=self._normalize(text), source_indices=source_indices
        )

    def _normalize(self, text: str) -> str:
        # 标点补全和空白清理
        text = text.strip()
        if not text:
            return text
        # 移除开头的逗号/分号
        text = re.sub(r"^[,，;；]\s*", "", text)
        # 句末无标点则补句号
        if not SENTENCE_END.search(text):
            text += "。"
        return text

    def _split_long(self, text: str) -> list[str]:
        # 在逗号/分号处切分长句，返回多段列表
        # 找切分点
        splits = []
        for m in CLAUSE_SEP.finditer(text):
            pos = m.end()
            # 从上一个切分点到当前，如果段长>20就切
            prev = splits[-1] if splits else 0
            seg_len = pos - prev
            if seg_len >= 20:
                splits.append(pos)

        if not splits:
            # 没有合适切分点则保持原样
            return [text]

        # 按切分点拆分
        parts = []
        prev = 0
        for sp in splits:
            parts.append(text[prev:sp])
            prev = sp
        if prev < len(text):
            parts.append(text[prev:])

        return parts


    def finalize(self, sentences: list[str]) -> list[str]:
        if not sentences:
            return []

        # 第一遍：合并过短碎片
        merged = self._merge_fragments(sentences)

        # 第二遍：切分过长句标点补全
        result = []
        for s in merged:
            s = s.strip()
            if not s:
                continue
            if len(s) > self.max_chars:
                parts = self._split_long(s)
                result.extend(self._normalize(p) for p in parts if p.strip())
            else:
                result.append(self._normalize(s))

        # 第三遍：再次合并可能产生的碎片
        result = self._merge_fragments(result)

        return result

    def _merge_fragments(self, sentences: list[str]) -> list[str]:
        # 合并过短碎片。
        if not sentences:
            return []

        result = []
        pending = ""

        for s in sentences:
            s = s.strip()
            if not s:
                continue

            if len(s) < self.merge_min_chars and not SENTENCE_END.search(s):
                # 碎片 → 积累
                pending += s
            else:
                if pending:
                    # 把积累的碎片附加到当前句前面
                    s = pending + s
                    pending = ""
                result.append(s)

        # 残余碎片附加到最后一句
        if pending:
            if result:
                result[-1] = result[-1] + pending
            else:
                result.append(pending)

        return result



def create_default_processor() -> SentenceProcessor:
    # 创建默认配置的处理器实例。
    return SentenceProcessor(
        min_chars=MIN_CHARS,
        max_chars=MAX_CHARS,
        merge_min_chars=MERGE_MIN_CHARS,
    )
