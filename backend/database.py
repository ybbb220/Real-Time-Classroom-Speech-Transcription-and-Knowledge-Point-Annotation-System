# 数据库连接管理模块。
#
# 不在 import 时建立连接，避免启动时宕机和连接超时问题。
# 每次请求通过 get_db() 获取连接，使用完后调用 close_db() 归还。

import pymysql
from contextlib import contextmanager
from config import MYSQL_HOST, MYSQL_PORT, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DATABASE


def _create_connection():
    return pymysql.connect(
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=MYSQL_DATABASE,
        charset="utf8mb4",
        autocommit=False,
        cursorclass=pymysql.cursors.Cursor,
    )


def init_db():
    # 创建应用所需的数据库表（如不存在）。
    with get_db() as conn:
        cursor = conn.cursor()
        # 用户表
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS user (
                id INT PRIMARY KEY AUTO_INCREMENT,
                username VARCHAR(50) NOT NULL UNIQUE,
                password VARCHAR(100) NOT NULL,
                create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        # 知识点表
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS knowledge (
                id INT AUTO_INCREMENT PRIMARY KEY,
                content VARCHAR(500) NOT NULL COMMENT '知识点内容',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        print("[DB] 数据库表初始化完成")


@contextmanager
def get_db():
    # 获取数据库连接的上下文管理器，退出时自动提交/回滚并关闭。
    #
    # 用法:
    #     with get_db() as conn:
    #         cursor = conn.cursor()
    #         cursor.execute("SELECT ...")
    #         return cursor.fetchall()
    conn = _create_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
