#!/usr/bin/env python3
import sys
import os

# 将项目根目录加入 python 模块搜索路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# 加载 .env 环境变量
env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.env"))
if os.path.exists(env_path):
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#"):
                key, val = line.split("=", 1)
                os.environ[key.strip()] = val.strip()

from backend.db import DatabaseFacade
from backend.auth import hash_password

def add_user(username: str, email: str, password_raw: str):
    db_path = os.getenv("DATABASE_PATH", "data/project.db")
    print(f"Using database path: {db_path}")
    
    # 实例化 DatabaseFacade
    db = DatabaseFacade(db_path)
    
    # 检查用户是否已存在
    existing_user = db.users.get_by_email(email)
    if existing_user:
        print(f"User with email '{email}' already exists: {existing_user['username']} ({existing_user['uuid']})")
        return
    
    # 对密码进行哈希
    pw_hash = hash_password(password_raw)
    
    # 插入用户
    try:
        user = db.users.create(username=username, email=email, password_hash=pw_hash)
        print(f"User successfully created!")
        print(f"UUID: {user['uuid']}")
        print(f"Username: {user['username']}")
        print(f"Email: {user['email']}")
    except Exception as e:
        print(f"Error creating user: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    username = "user"
    email = "user@example.com"
    password = "admin114514"
    
    add_user(username, email, password)
