from flask import jsonify


def ok(msg="success", data=None):
    body = {"code": 200, "msg": msg}
    if data is not None:
        body["data"] = data
    return jsonify(body)


def err(code: int, msg: str):
    return jsonify({"code": code, "msg": msg})
