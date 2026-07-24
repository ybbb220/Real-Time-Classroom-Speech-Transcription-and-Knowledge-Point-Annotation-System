from flask import Blueprint, request
from services.auth_service import find_user_by_username, create_user
from utils.password import check_pwd
from utils.response import ok, err
from utils.auth import generate_token, remove_token

auth_bp = Blueprint("auth", __name__, url_prefix="/api")


def _get_credentials():
    # 从请求体中提取并校验 username / password
    data = request.get_json(silent=True)
    if not data:
        return None, err(400, "请求体不能为空，需要 JSON 格式")

    username = (data.get("username") or "").strip()
    password = (data.get("password") or "")

    if not username:
        return None, err(400, "用户名不能为空")
    if not password:
        return None, err(400, "密码不能为空")
    if len(username) > 64:
        return None, err(400, "用户名过长")
    if len(password) > 128:
        return None, err(400, "密码过长")

    return {"username": username, "password": password}, None


@auth_bp.post("/register")
def register():
    creds, error = _get_credentials()
    if error:
        return error

    username, password = creds["username"], creds["password"]

    if find_user_by_username(username):
        return err(400, "用户名已存在")

    create_user(username, password)
    token = generate_token(username)
    return ok("注册成功", {"token": token, "username": username})


@auth_bp.post("/login")
def login():
    creds, error = _get_credentials()
    if error:
        return error

    username, password = creds["username"], creds["password"]

    row = find_user_by_username(username)
    if not row or not check_pwd(password, row[2]):
        return err(401, "用户名或密码错误")

    token = generate_token(username)
    return ok("登录成功", {"token": token, "username": username})


@auth_bp.post("/logout")
def logout():
    # 退出登录，使 token 失效。
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        remove_token(auth_header[7:])
    return ok("已退出登录")
