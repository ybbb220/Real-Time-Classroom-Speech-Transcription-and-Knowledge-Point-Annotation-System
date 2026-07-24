from database import get_db
from utils.password import hash_pwd

def find_user_by_username(username: str):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, username, password FROM user WHERE username=%s", (username,)
        )
        return cursor.fetchone()

def create_user(username: str, password: str):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO user(username, password) VALUES(%s, %s)",
            (username, hash_pwd(password)),
        )
