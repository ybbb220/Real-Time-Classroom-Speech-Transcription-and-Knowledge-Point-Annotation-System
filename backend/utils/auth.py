import secrets
from functools import wraps
from flask import request, jsonify

# token → username 映射（进程生命周期内有效）
_token_store: dict[str, str] = {}


def generate_token(username: str) -> str:
    # 为新登录用户生成token 返回token字符串
    token = secrets.token_hex(32)
    _token_store[token] = username
    return token


def remove_token(token: str) -> None:
    # 登出时移除token
    _token_store.pop(token, None)


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"code": 401, "msg": "未登录，请先登录"}), 401

        token = auth_header[7:]  # 去掉"Bearer "前缀
        if token not in _token_store:
            return jsonify({"code": 401, "msg": "登录已过期，请重新登录"}), 401

        # 把用户名注入请求上下文，方便后续使用
        request.current_user = _token_store[token]
        return f(*args, **kwargs)

    return decorated
