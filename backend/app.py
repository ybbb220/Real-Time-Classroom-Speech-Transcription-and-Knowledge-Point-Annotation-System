import os
from flask import Flask
from flask_cors import CORS
from database import init_db
from routes.auth import auth_bp
from routes.asr import asr_bp
from routes.knowledge import knowledge_bp

app = Flask(__name__)
CORS(app)
app.register_blueprint(auth_bp)
app.register_blueprint(asr_bp)
app.register_blueprint(knowledge_bp)

try:
    init_db()
except Exception as e:
    print(f"[WARNING] 数据库初始化失败，请检查 MySQL 连接: {e}")
    print("[WARNING] 涉及数据库的功能（登录/注册/知识库）将不可用")


if __name__ == "__main__":
    debug = os.getenv("FLASK_DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=5000, debug=debug)
