import os
import json
import queue
import threading
from flask import Blueprint, request, Response
from werkzeug.utils import secure_filename

from utils.response import ok, err
from utils.auth import login_required
from services.asr_service import transcribe_audio_file

asr_bp = Blueprint("asr", __name__, url_prefix="/api")

ALLOWED_EXTENSIONS = {"pcm", "wav"}
UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads")


def _allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


@asr_bp.route("/asr", methods=["POST"])
@login_required
def transcribe():
    # 检查文件
    if "audio" not in request.files:
        return err(400, "请上传音频文件（字段名: audio）")

    file = request.files["audio"]
    if file.filename == "":
        return err(400, "未选择文件")

    if not _allowed_file(file.filename):
        return err(400, f"仅支持 {', '.join(ALLOWED_EXTENSIONS)} 格式的音频文件")

    # 保存到 uploads/
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    filename = secure_filename(file.filename)
    filepath = os.path.join(UPLOAD_DIR, filename)
    file.save(filepath)

    # 转写+知识标注
    try:
        result = transcribe_audio_file(filepath)
    except Exception as e:
        return err(500, f"语音转写失败: {str(e)}")

    # 返回
    return ok("转写完成", {
        "full_text": result.full_text.strip(),
        "sentences": [
            {
                "text": s["text"],
                "knowledge": s["knowledge"],
            }
            for s in result.sentences
        ],
    })


@asr_bp.route("/asr/stream", methods=["POST"])
@login_required
def transcribe_stream():
    # 检查文件
    if "audio" not in request.files:
        return err(400, "请上传音频文件（字段名: audio）")

    file = request.files["audio"]
    if file.filename == "":
        return err(400, "未选择文件")

    if not _allowed_file(file.filename):
        return err(400, f"仅支持 {', '.join(ALLOWED_EXTENSIONS)} 格式的音频文件")

    # 保存到 uploads/
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    filename = secure_filename(file.filename)
    filepath = os.path.join(UPLOAD_DIR, filename)
    file.save(filepath)

    # 创建队列桥接转写线程和 SSE 生成器
    q: queue.Queue = queue.Queue()

    def on_sentence(text: str, knowledge: list):
        # 每句定稿后的流式回调：将结果推入队列。
        q.put({"type": "sentence", "text": text, "knowledge": knowledge})

    def _run_transcription():
        # 在后台线程中执行转写，完成后发送结束信号。
        try:
            result = transcribe_audio_file(filepath, on_sentence=on_sentence)
            q.put({
                "type": "complete",
                "full_text": result.full_text.strip(),
                "sentence_count": len(result.sentences),
            })
        except Exception as e:
            q.put({"type": "error", "message": str(e)})

    # 启动后台转写线程
    thread = threading.Thread(target=_run_transcription, daemon=True)
    thread.start()

    # 流式响应生成器
    def generate():
        yield json.dumps({"type": "start"}, ensure_ascii=False) + "\n"

        while True:
            try:
                event = q.get(timeout=360)
                yield json.dumps(event, ensure_ascii=False) + "\n"
                if event["type"] in ("complete", "error"):
                    break
            except queue.Empty:
                yield json.dumps(
                    {"type": "error", "message": "转写超时，请检查音频格式和 API 配置"},
                    ensure_ascii=False,
                ) + "\n"
                break

    return Response(
        generate(),
        mimetype="application/x-ndjson",
        headers={
            "X-Accel-Buffering": "no",       # 禁用 nginx 缓冲
            "Cache-Control": "no-cache",      # 禁用浏览器缓存
            "X-Content-Type-Options": "nosniff",
        },
    )
