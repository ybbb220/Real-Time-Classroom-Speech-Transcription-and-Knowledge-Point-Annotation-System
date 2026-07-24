import logging
import os
import base64
import signal
import struct
import sys
import threading
import time
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError

from dashscope.audio.qwen_omni import (
    OmniRealtimeCallback,
    OmniRealtimeConversation,
    MultiModality,
)
from dashscope.audio.qwen_omni.omni_realtime import TranscriptionParams
import dashscope

from config import DASHSCOPE_WS_URL
from services.faiss_service import get_retriever, BGERetriever
from services.knowledge_service import get_all_docs
from services.text_processor import SentenceProcessor, create_default_processor


@dataclass
class ASRResult:

    full_text: str = ""  # 拼接后的完整转写文本
    sentences: list = field(default_factory=list)  # [{"text": str, "knowledge": [...]}]



class MyCallback(OmniRealtimeCallback):


    def __init__(self, conversation, retriever: BGERetriever, result: ASRResult = None,
                 on_sentence: callable = None, processor: SentenceProcessor = None):
        self.conversation = conversation
        self.retriever = retriever
        self.result = result  # 可选的结果收集器
        self.on_sentence = on_sentence
        self.processor = processor or create_default_processor()  # 句子后处理器
        self._buf = ""
        self._last_len = 0
        self.handlers = {
            "session.created": lambda r: None,
            "conversation.item.input_audio_transcription.text": self._on_text,
            "conversation.item.input_audio_transcription.completed": self._on_final,
            "input_audio_buffer.speech_started": lambda r: None,
            "input_audio_buffer.speech_stopped": lambda r: None,
        }

    def on_open(self):
        pass

    def on_close(self, code, msg):
        pass

    def on_event(self, response):
        try:
            h = self.handlers.get(response.get("type"))
            if h:
                h(response)
        except Exception as e:
            print(f"[Error] {e}")

    def _on_text(self, r):
        t = r.get("text", "") + r.get("stash", "")
        new = t[self._last_len :]
        if new:
            sys.stdout.write(new)
            sys.stdout.flush()
            self._last_len = len(t)
        self._buf = t

    def _on_final(self, r):
        raw_sentence = r["transcript"].strip()
        sys.stdout.write("  🔎\n")
        sys.stdout.flush()

        processed = self.processor.feed(raw_sentence)

        if processed is None:
            self._buf = ""
            self._last_len = 0
            return

        self._do_search_and_emit(processed)

        self._buf = ""
        self._last_len = 0

    def flush_processor(self):
        remaining = self.processor.flush()
        if remaining:
            self._do_search_and_emit(remaining)
        return remaining

    def _do_search_and_emit(self, sentence: str):
        hits = self.retriever.search(sentence, k=3)
        for h in hits:
            print(
                f"    [FAISS] Top{h['rank']} 相似度={h['score']:.4f} → {h['doc']}"
            )

        knowledge = [
            {"rank": h["rank"], "score": h["score"], "doc": h["doc"]}
            for h in hits
        ]

        if self.result is not None:
            self.result.full_text += sentence + "\n"
            self.result.sentences.append({"text": sentence, "knowledge": knowledge})

        if self.on_sentence is not None:
            try:
                self.on_sentence(sentence, knowledge)
            except Exception as e:
                print(f"[Error] on_sentence 回调异常: {e}")


# 工具函数
def setup_logging():
    logger = logging.getLogger("dashscope")
    logger.setLevel(logging.DEBUG)
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.DEBUG)
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.propagate = False
    return logger


def init_api_key():
    dashscope.api_key = os.environ.get("DASHSCOPE_API_KEY", "YOUR_API_KEY")
    if dashscope.api_key == "YOUR_API_KEY":
        print(
            "[Warning] Using placeholder API key, "
            "set DASHSCOPE_API_KEY environment variable."
        )


def _parse_wav_header(file_path: str) -> tuple[int, dict | None]:
    with open(file_path, "rb") as f:
        riff = f.read(12)
        if len(riff) < 12 or riff[0:4] != b"RIFF" or riff[8:12] != b"WAVE":
            return 0, None

        fmt_info = None
        pcm_offset = 0

        while True:
            chunk_header = f.read(8)
            if len(chunk_header) < 8:
                break
            chunk_id = chunk_header[0:4]
            chunk_size = struct.unpack("<I", chunk_header[4:8])[0]

            if chunk_id == b"fmt ":
                fmt_data = f.read(chunk_size)
                if len(fmt_data) >= 16:
                    audio_format, channels = struct.unpack("<HH", fmt_data[0:4])
                    sample_rate = struct.unpack("<I", fmt_data[4:8])[0]
                    bits_per_sample = struct.unpack("<H", fmt_data[14:16])[0]
                    fmt_info = {
                        "sample_rate": sample_rate,
                        "channels": channels,
                        "bits_per_sample": bits_per_sample,
                        "audio_format": audio_format,  # 1 = PCM
                    }
            elif chunk_id == b"data":
                pcm_offset = f.tell()
                if fmt_info is not None:
                    break
            else:
                f.seek(chunk_size, 1)

        return pcm_offset, fmt_info


def _find_wav_pcm_offset(f) -> int:
    riff = f.read(12)
    if len(riff) < 12:
        f.seek(0)
        return 0
    if riff[0:4] != b"RIFF" or riff[8:12] != b"WAVE":
        f.seek(0)
        return 0

    while True:
        chunk_header = f.read(8)
        if len(chunk_header) < 8:
            break
        chunk_id = chunk_header[0:4]
        chunk_size = struct.unpack("<I", chunk_header[4:8])[0]

        if chunk_id == b"data":
            return f.tell()

        f.seek(chunk_size, 1)

    f.seek(0)
    return 0


def read_audio_chunks(file_path, chunk_size=3200):
    # 按块读取音频文件的 PCM 数据。自动识别并剥离 WAV 文件头。
    with open(file_path, "rb") as f:
        offset = _find_wav_pcm_offset(f)
        if offset > 0:
            print(f"[Audio] 检测到 WAV 格式，跳过头 {offset} 字节")
        while chunk := f.read(chunk_size):
            yield chunk


def send_audio(conversation, file_path, delay=0.1):
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Audio file {file_path} does not exist.")
    print("Processing audio file... Press 'Ctrl+C' to stop.")
    for chunk in read_audio_chunks(file_path):
        audio_b64 = base64.b64encode(chunk).decode("ascii")
        conversation.append_audio(audio_b64)
        time.sleep(delay)



DEFAULT_TRANSCRIBE_TIMEOUT = 300  # 5分钟超时时间


def transcribe_audio_file(
    file_path: str,
    kb_docs: list[str] = None,
    delay: float = 0.02,
    timeout: int = DEFAULT_TRANSCRIBE_TIMEOUT,
    on_sentence: callable = None,
) -> ASRResult:
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"音频文件不存在: {file_path}")

    pcm_offset, fmt_info = _parse_wav_header(file_path)
    if fmt_info is not None:
        print(
            f"[Audio] WAV 格式: {fmt_info['sample_rate']}Hz "
            f"{fmt_info['channels']}ch {fmt_info['bits_per_sample']}bit"
        )
        if fmt_info["channels"] != 1:
            raise ValueError(
                f"仅支持单声道音频，当前为 {fmt_info['channels']} 声道"
            )
        if fmt_info["sample_rate"] != 16000:
            raise ValueError(
                f"仅支持 16000Hz 采样率，当前为 {fmt_info['sample_rate']}Hz。"
                f"请使用音频工具转换: ffmpeg -i input.wav -ar 16000 -ac 1 -sample_fmt s16 output.wav"
            )
        if fmt_info["bits_per_sample"] != 16:
            raise ValueError(
                f"仅支持 16bit 位深，当前为 {fmt_info['bits_per_sample']}bit"
            )
        if fmt_info.get("audio_format") != 1:
            raise ValueError(
                f"仅支持 PCM 编码的 WAV，当前编码格式为 {fmt_info['audio_format']}"
            )
    init_api_key()

    if kb_docs is None:
        kb_docs = get_all_docs()

    retriever = get_retriever(docs=kb_docs)
    result = ASRResult()
    error_ref: list[Exception] = []  # 跨线程传递异常

    def _run_conversation():
        # 在后台线程中运行 WebSocket 对话（可被超时中断）。
        nonlocal result
        callback = MyCallback(conversation=None, retriever=retriever, result=result,
                              on_sentence=on_sentence)
        conversation = OmniRealtimeConversation(
            model="qwen3-asr-flash-realtime",
            url=DASHSCOPE_WS_URL,
            callback=callback,
        )
        callback.conversation = conversation

        try:
            conversation.connect()

            transcription_params = TranscriptionParams(
                language="zh", sample_rate=16000, input_audio_format="pcm"
            )
            conversation.update_session(
                output_modalities=[MultiModality.TEXT],
                enable_input_audio_transcription=True,
                transcription_params=transcription_params,
            )

            print(f"Processing audio file: {file_path}")
            for chunk in read_audio_chunks(file_path):
                audio_b64 = base64.b64encode(chunk).decode("ascii")
                conversation.append_audio(audio_b64)
                time.sleep(delay)
            conversation.end_session()
            callback.flush_processor()
        except Exception as e:
            error_ref.append(e)
            raise
        finally:
            conversation.close()
            print("Audio processing completed.")

    # 4. 在独立线程中运行，带超时保护
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_run_conversation)
        try:
            future.result(timeout=timeout)
        except FutureTimeoutError:
            raise TimeoutError(
                f"语音转写超时（{timeout}秒），请检查：\n"
                "  1. DashScope API Key 是否有效\n"
                "  2. 网络是否能访问阿里云 DashScope\n"
                "  3. 音频文件是否为 16kHz 单声道 16bit"
            )

    if error_ref:
        raise error_ref[0]

    return result


if __name__ == "__main__":
    setup_logging()
    audio_file_path = "./your_audio_file.pcm"  # 16k s16le pcm
    result = transcribe_audio_file(audio_file_path)
    print("\n===== 转写结果 =====")
    print(result.full_text)
    print("===== 逐句知识点 =====")
    for s in result.sentences:
        print(f"  📝 {s['text']}")
        for k in s["knowledge"]:
            print(f"     🏷 Top{k['rank']} ({k['score']:.4f}) → {k['doc']}")
        if not s["knowledge"]:
            print("     (无匹配知识点)")
