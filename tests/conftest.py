"""社区功能测试公共工具：每个测试用独立 sqlite + 独立 data 目录。
通过 monkeypatch 把 backend.community.db 与 backend.config.BASE_DIR 切换到 tmp 路径，避免污染开发数据库。"""
from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def isolated_app(tmp_path, monkeypatch):
    """构造一份与 main.app 等价但所有持久化都指向 tmp_path 的 FastAPI 应用。"""
    db_path = tmp_path / "test.db"
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    skills_dir = data_dir / "skills"
    skills_dir.mkdir()

    # 关键：覆盖 BASE_DIR 让 UserFile 起 tmp 目录
    monkeypatch.setattr("backend.config.BASE_DIR", tmp_path)
    monkeypatch.setattr("backend.config.DATABASE_PATH", str(db_path))
    monkeypatch.setattr("backend.config.SKILL_STORAGE_DIR", str(skills_dir))
    monkeypatch.setattr("backend.config.JWT_SECRET", "test-secret")

    # 子模块在 import 时已经把 DATABASE_PATH/JWT_SECRET 拼成局部变量，需要分别覆盖
    monkeypatch.setattr("backend.auth.JWT_SECRET", "test-secret")
    monkeypatch.setattr("backend.file.BASE_DIR", tmp_path)

    from backend.db import DatabaseFacade
    from backend.db_dep import get_db

    facade = DatabaseFacade(db_path=str(db_path))
    facade.setup_database()

    # 用 FastAPI 的 dependency_overrides 替换 get_db，确保所有 Depends(get_db) 都注入测试 facade
    from backend.community import router as community_router
    from backend.auth import router as auth_router
    from fastapi import FastAPI

    app = FastAPI()
    app.dependency_overrides[get_db] = lambda: facade
    app.include_router(auth_router)
    app.include_router(community_router)

    return app, facade


@pytest.fixture
def client(isolated_app):
    app, _facade = isolated_app
    with TestClient(app) as c:
        yield c


@pytest.fixture
def facade(isolated_app):
    _app, facade = isolated_app
    return facade


def _register_and_login(client: TestClient, email: str, username: str = "alice", password: str = "password123") -> str:
    """注册账号并登录，返回 access_token。"""
    r = client.post(
        "/auth/register",
        json={"username": username, "email": email, "password": password},
    )
    assert r.status_code == 201, r.text
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture
def alice_token(client):
    return _register_and_login(client, email="alice@example.com", username="alice")


@pytest.fixture
def bob_token(client):
    return _register_and_login(client, email="bob@example.com", username="bob", password="password456")


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def nonce_headers(token: str, suffix: str = "") -> dict[str, str]:
    """带 X-Nonce 的请求头。每次调用生成唯一 nonce。"""
    import uuid
    nonce = str(uuid.uuid4()) + suffix
    return {
        "Authorization": f"Bearer {token}",
        "X-Nonce": nonce,
        "X-Nonce-Timestamp": str(time.time()),
    }


def make_skill_md(name: str = "demo-skill", description: str = "示例技能") -> str:
    return f"""---
name: {name}
description: {description}
---

# 技能说明
这是一个测试 skill。"""
