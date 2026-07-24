from flask import Blueprint, request, Response

from utils.response import ok, err
from utils.auth import login_required
from services.knowledge_service import (
    list_knowledge,
    add_knowledge,
    update_knowledge,
    delete_knowledge,
    generate_docx,
)

knowledge_bp = Blueprint("knowledge", __name__, url_prefix="/api")


def _get_content_from_body():
    # 从请求 JSON 体中提取 content 字段并校验
    data = request.get_json(silent=True)
    if not data:
        return None, err(400, "请求体不能为空，需要 JSON 格式")
    content = (data.get("content") or "").strip()
    if not content:
        return None, err(400, "知识点内容不能为空")
    if len(content) > 500:
        return None, err(400, "知识点内容不能超过 500 字")
    return content, None


@knowledge_bp.route("/knowledge", methods=["GET"])
@login_required
def list_api():
    # 获取全部知识点列表
    items = list_knowledge()
    return ok("查询成功", items)


@knowledge_bp.route("/knowledge", methods=["POST"])
@login_required
def add_api():
    # 新增知识点
    content, error = _get_content_from_body()
    if error:
        return error
    new_id = add_knowledge(content)
    return ok("添加成功", {"id": new_id, "content": content})


@knowledge_bp.route("/knowledge/<int:knowledge_id>", methods=["PUT"])
@login_required
def update_api(knowledge_id):
    # 更新知识点
    content, error = _get_content_from_body()
    if error:
        return error
    if not update_knowledge(knowledge_id, content):
        return err(404, "知识点不存在")
    return ok("更新成功")


@knowledge_bp.route("/knowledge/<int:knowledge_id>", methods=["DELETE"])
@login_required
def delete_api(knowledge_id):
    # 删除知识点
    if not delete_knowledge(knowledge_id):
        return err(404, "知识点不存在")
    return ok("删除成功")


@knowledge_bp.route("/knowledge/export", methods=["POST"])
@login_required
def export_docx():
    # 导出知识点覆盖清单为 Word 文档
    data = request.get_json(silent=True)
    if not data or not isinstance(data.get("items"), list):
        return err(400, "请求体需要包含 items 列表")
    items = data["items"]
    if not items:
        return err(400, "items 列表不能为空")

    buf = generate_docx(items)
    filename = "知识点覆盖清单.docx"
    return Response(
        buf.read(),
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{_url_quote(filename)}"
        }
    )


def _url_quote(s: str) -> str:
    # 对非 ASCII 文件名做 URL 编码
    from urllib.parse import quote
    return quote(s, safe="")
