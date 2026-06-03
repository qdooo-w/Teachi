import io
import pytest
from pathlib import Path
from fastapi import FastAPI
from fastapi.testclient import TestClient
from backend.db import DatabaseFacade
from backend.db_dep import get_db
from backend.auth import router as auth_router
from backend.data import router as data_router

@pytest.fixture
def isolated_api_env(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    
    monkeypatch.setattr("backend.config.BASE_DIR", tmp_path)
    monkeypatch.setattr("backend.config.DATABASE_PATH", str(db_path))
    monkeypatch.setattr("backend.auth.JWT_SECRET", "test-secret")
    monkeypatch.setattr("backend.file.BASE_DIR", tmp_path)
    monkeypatch.setattr("backend.data.BASE_DIR", tmp_path)
    monkeypatch.setattr("backend.transfer.BASE_DIR", tmp_path)
    
    facade = DatabaseFacade(db_path=str(db_path))
    facade.setup_database()
    
    app = FastAPI()
    app.dependency_overrides[get_db] = lambda: facade
    app.include_router(auth_router)
    app.include_router(data_router)
    
    with TestClient(app) as client:
        yield client, facade, tmp_path
        
    app.dependency_overrides.clear()


def register_and_login(client: TestClient, email: str, username: str = "alice", password: str = "password123") -> str:
    r = client.post(
        "/auth/register",
        json={"username": username, "email": email, "password": password},
    )
    assert r.status_code == 201, r.text
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def test_normal_upload(isolated_api_env):
    client, facade, tmp_path = isolated_api_env
    token = register_and_login(client, "alice@example.com")
    user = facade.users.get_by_email("alice@example.com")
    user_uuid = user["uuid"]
    
    # Create project and session via API
    headers = {"Authorization": f"Bearer {token}"}
    r = client.post(f"/users/{user_uuid}/projects", json={"projectname": "p1"}, headers=headers)
    assert r.status_code == 201
    pid = r.json()["pid"]
    
    r = client.post(f"/projects/{pid}/sessions", json={"sessionname": "s1"}, headers=headers)
    assert r.status_code == 201
    sid = r.json()["sid"]
    
    # Normal PNG upload
    png_content = b"\x89PNG\r\n\x1a\nblahblah"
    file_payload = {"file": ("test.png", io.BytesIO(png_content), "image/png")}
    
    r = client.post(f"/sessions/{sid}/attachments", files=file_payload, headers=headers)
    assert r.status_code == 201
    data = r.json()
    assert "attachment_id" in data
    assert data["original_filename"] == "图片1.png"
    assert data["mime_type"] == "image/png"
    assert "created_at" in data
    
    # Check DB record
    attachment_id = data["attachment_id"]
    db_record = facade.attachments.get_for_user(attachment_id, user_uuid)
    assert db_record is not None
    assert db_record["sid"] == sid
    assert db_record["original_filename"] == "图片1.png"
    assert db_record["mime_type"] == "image/png"
    
    # Check physical file exists
    physical_path = tmp_path / db_record["file_path"]
    assert physical_path.exists()
    assert physical_path.read_bytes() == png_content

    # Normal JPEG upload
    jpeg_content = b"\xff\xd8\xffblahblah"
    file_payload = {"file": ("test.jpg", io.BytesIO(jpeg_content), "image/jpeg")}
    r = client.post(f"/sessions/{sid}/attachments", files=file_payload, headers=headers)
    assert r.status_code == 201


def test_upload_non_image_allowed(isolated_api_env):
    client, facade, tmp_path = isolated_api_env
    token = register_and_login(client, "alice@example.com")
    user = facade.users.get_by_email("alice@example.com")
    user_uuid = user["uuid"]
    
    headers = {"Authorization": f"Bearer {token}"}
    r = client.post(f"/users/{user_uuid}/projects", json={"projectname": "p1"}, headers=headers)
    pid = r.json()["pid"]
    r = client.post(f"/projects/{pid}/sessions", json={"sessionname": "s1"}, headers=headers)
    sid = r.json()["sid"]
    
    # Try uploading text/plain file (should be allowed now)
    file_payload = {"file": ("test.txt", io.BytesIO(b"hello world"), "text/plain")}
    r = client.post(f"/sessions/{sid}/attachments", files=file_payload, headers=headers)
    assert r.status_code == 201
    assert r.json()["original_filename"] == "文档1.txt"


def test_magic_bytes_mismatch_blocked(isolated_api_env):
    client, facade, tmp_path = isolated_api_env
    token = register_and_login(client, "alice@example.com")
    user = facade.users.get_by_email("alice@example.com")
    user_uuid = user["uuid"]
    
    headers = {"Authorization": f"Bearer {token}"}
    r = client.post(f"/users/{user_uuid}/projects", json={"projectname": "p1"}, headers=headers)
    pid = r.json()["pid"]
    r = client.post(f"/projects/{pid}/sessions", json={"sessionname": "s1"}, headers=headers)
    sid = r.json()["sid"]
    
    # Send content that says image/png but starts with b"hello"
    file_payload = {"file": ("test.png", io.BytesIO(b"hello png content"), "image/png")}
    r = client.post(f"/sessions/{sid}/attachments", files=file_payload, headers=headers)
    assert r.status_code == 400
    assert "Magic bytes validation failed" in r.json()["detail"]["message"]


def test_upload_too_large_blocked(isolated_api_env, monkeypatch):
    client, facade, tmp_path = isolated_api_env
    monkeypatch.setattr("backend.config.ATTACHMENT_MAX_BYTES", 20 * 1024 * 1024)
    monkeypatch.setattr("backend.data.ATTACHMENT_MAX_BYTES", 20 * 1024 * 1024)
    token = register_and_login(client, "alice@example.com")
    user = facade.users.get_by_email("alice@example.com")
    user_uuid = user["uuid"]
    
    headers = {"Authorization": f"Bearer {token}"}
    r = client.post(f"/users/{user_uuid}/projects", json={"projectname": "p1"}, headers=headers)
    pid = r.json()["pid"]
    r = client.post(f"/projects/{pid}/sessions", json={"sessionname": "s1"}, headers=headers)
    sid = r.json()["sid"]
    
    # Generate content larger than 20MB
    large_content = b"\x89PNG" + b"x" * (20 * 1024 * 1024 + 1)
    file_payload = {"file": ("large.png", io.BytesIO(large_content), "image/png")}
    r = client.post(f"/sessions/{sid}/attachments", files=file_payload, headers=headers)
    assert r.status_code == 400
    assert "exceeds 20MB limit" in r.json()["detail"]["message"]


def test_list_attachments(isolated_api_env):
    client, facade, tmp_path = isolated_api_env
    token = register_and_login(client, "alice@example.com")
    user = facade.users.get_by_email("alice@example.com")
    user_uuid = user["uuid"]
    
    headers = {"Authorization": f"Bearer {token}"}
    r = client.post(f"/users/{user_uuid}/projects", json={"projectname": "p1"}, headers=headers)
    pid = r.json()["pid"]
    r = client.post(f"/projects/{pid}/sessions", json={"sessionname": "s1"}, headers=headers)
    sid = r.json()["sid"]
    
    # Upload first
    png_content = b"\x89PNG\r\n\x1a\nblahblah"
    file_payload = {"file": ("test.png", io.BytesIO(png_content), "image/png")}
    r = client.post(f"/sessions/{sid}/attachments", files=file_payload, headers=headers)
    assert r.status_code == 201
    attachment_id = r.json()["attachment_id"]
    
    # List attachments
    r = client.get(f"/sessions/{sid}/attachments", headers=headers)
    assert r.status_code == 200
    res = r.json()
    assert "attachments" in res
    assert len(res["attachments"]) == 1
    item = res["attachments"][0]
    assert item["attachment_id"] == attachment_id
    assert item["original_filename"] == "图片1.png"
    assert item["mime_type"] == "image/png"
    assert item["anchor_msg_id"] is None
    assert item["has_description"] is False


def test_delete_attachment(isolated_api_env):
    client, facade, tmp_path = isolated_api_env
    token = register_and_login(client, "alice@example.com")
    user = facade.users.get_by_email("alice@example.com")
    user_uuid = user["uuid"]
    
    headers = {"Authorization": f"Bearer {token}"}
    r = client.post(f"/users/{user_uuid}/projects", json={"projectname": "p1"}, headers=headers)
    pid = r.json()["pid"]
    r = client.post(f"/projects/{pid}/sessions", json={"sessionname": "s1"}, headers=headers)
    sid = r.json()["sid"]
    
    # Upload
    png_content = b"\x89PNG\r\n\x1a\nblahblah"
    file_payload = {"file": ("test.png", io.BytesIO(png_content), "image/png")}
    r = client.post(f"/sessions/{sid}/attachments", files=file_payload, headers=headers)
    assert r.status_code == 201
    data = r.json()
    attachment_id = data["attachment_id"]
    
    # Check that record and file exist
    db_record = facade.attachments.get_for_user(attachment_id, user_uuid)
    assert db_record is not None
    physical_path = tmp_path / db_record["file_path"]
    assert physical_path.exists()
    
    # Delete
    r = client.delete(f"/sessions/{sid}/attachments/{attachment_id}", headers=headers)
    assert r.status_code == 204
    
    # Check DB record is deleted
    assert facade.attachments.get_for_user(attachment_id, user_uuid) is None
    
    # Check physical file is deleted
    assert not physical_path.exists()


def test_directory_cleanups(isolated_api_env):
    client, facade, tmp_path = isolated_api_env
    token = register_and_login(client, "alice@example.com")
    user = facade.users.get_by_email("alice@example.com")
    user_uuid = user["uuid"]
    
    headers = {"Authorization": f"Bearer {token}"}
    r = client.post(f"/users/{user_uuid}/projects", json={"projectname": "p1"}, headers=headers)
    pid = r.json()["pid"]
    r = client.post(f"/projects/{pid}/sessions", json={"sessionname": "s1"}, headers=headers)
    sid = r.json()["sid"]
    
    # Upload an attachment to create physical directory structures
    png_content = b"\x89PNG\r\n\x1a\nblahblah"
    file_payload = {"file": ("test.png", io.BytesIO(png_content), "image/png")}
    r = client.post(f"/sessions/{sid}/attachments", files=file_payload, headers=headers)
    assert r.status_code == 201
    
    # Directories:
    # tmp_path / "data" / user_uuid / pid / sid
    session_dir = tmp_path / "data" / user_uuid / pid / sid
    project_dir = tmp_path / "data" / user_uuid / pid
    
    assert session_dir.exists()
    assert project_dir.exists()
    
    # Delete session
    r = client.delete(f"/sessions/{sid}", headers=headers)
    assert r.status_code == 204
    
    # Session directory should be deleted, but project directory should still exist
    assert not session_dir.exists()
    assert project_dir.exists()
    
    # Re-create session and upload another attachment
    r = client.post(f"/projects/{pid}/sessions", json={"sessionname": "s2"}, headers=headers)
    sid2 = r.json()["sid"]
    file_payload2 = {"file": ("test2.png", io.BytesIO(png_content), "image/png")}
    r = client.post(f"/sessions/{sid2}/attachments", files=file_payload2, headers=headers)
    assert r.status_code == 201
    
    session_dir2 = tmp_path / "data" / user_uuid / pid / sid2
    assert session_dir2.exists()
    assert project_dir.exists()
    
    # Delete project
    r = client.delete(f"/projects/{pid}", headers=headers)
    assert r.status_code == 204
    
    # Project directory (and all subdirs) should be recursively deleted
    assert not project_dir.exists()


def test_delete_active_turn_cleans_attachments(isolated_api_env):
    client, facade, tmp_path = isolated_api_env
    token = register_and_login(client, "alice@example.com")
    user = facade.users.get_by_email("alice@example.com")
    user_uuid = user["uuid"]

    # Create project and session
    headers = {"Authorization": f"Bearer {token}"}
    r = client.post(f"/users/{user_uuid}/projects", json={"projectname": "p1"}, headers=headers)
    pid = r.json()["pid"]
    r = client.post(f"/projects/{pid}/sessions", json={"sessionname": "s1"}, headers=headers)
    sid = r.json()["sid"]

    # Upload attachment
    png_content = b"\x89PNG\r\n\x1a\nblahblah"
    file_payload = {"file": ("test.png", io.BytesIO(png_content), "image/png")}
    r = client.post(f"/sessions/{sid}/attachments", files=file_payload, headers=headers)
    assert r.status_code == 201
    att_data = r.json()
    att_id = att_data["attachment_id"]

    # Create a message representing the turn
    msg = facade.messages.create(
        sid=sid,
        kind="user",
        raw_json="{}",
    )
    anchor_msg_id = msg["msg_id"]
    facade.messages.set_self_anchor(anchor_msg_id)

    # Bind attachment to this anchor
    facade.attachments.bind_anchor(
        attachment_ids=[att_id],
        anchor_msg_id=anchor_msg_id,
        user_uuid=user_uuid,
    )

    # Verify bound and physical file exists
    db_rec = facade.attachments.get_for_user(att_id, user_uuid)
    assert db_rec is not None
    assert db_rec["anchor_msg_id"] == anchor_msg_id
    physical_path = tmp_path / db_rec["file_path"]
    assert physical_path.exists()

    # Query using list_by_anchor
    bound_atts = facade.attachments.list_by_anchor(anchor_msg_id, user_uuid)
    assert len(bound_atts) == 1
    assert bound_atts[0]["attachment_id"] == att_id

    # Delete the turn
    r = client.delete(f"/messages/{anchor_msg_id}/turn", headers=headers)
    assert r.status_code == 204

    # Verify attachment DB record and physical file are both deleted!
    assert facade.attachments.get_for_user(att_id, user_uuid) is None
    assert not physical_path.exists()


def test_delete_active_turn_cleans_attachments_deduplicated(isolated_api_env):
    client, facade, tmp_path = isolated_api_env
    token = register_and_login(client, "alice@example.com")
    user = facade.users.get_by_email("alice@example.com")
    user_uuid = user["uuid"]

    # Create project and session
    headers = {"Authorization": f"Bearer {token}"}
    r = client.post(f"/users/{user_uuid}/projects", json={"projectname": "p1"}, headers=headers)
    pid = r.json()["pid"]
    r = client.post(f"/projects/{pid}/sessions", json={"sessionname": "s1"}, headers=headers)
    sid = r.json()["sid"]

    # Upload attachment 1 (first time)
    png_content = b"\x89PNG\r\n\x1a\nblahblah"
    file_payload = {"file": ("test1.png", io.BytesIO(png_content), "image/png")}
    r = client.post(f"/sessions/{sid}/attachments", files=file_payload, headers=headers)
    assert r.status_code == 201
    att_id1 = r.json()["attachment_id"]

    # Upload same attachment 2 (second time, deduplicated physically)
    file_payload2 = {"file": ("test2.png", io.BytesIO(png_content), "image/png")}
    r = client.post(f"/sessions/{sid}/attachments", files=file_payload2, headers=headers)
    assert r.status_code == 201
    att_id2 = r.json()["attachment_id"]

    # Create a message representing the turn
    msg = facade.messages.create(
        sid=sid,
        kind="user",
        raw_json="{}",
    )
    anchor_msg_id = msg["msg_id"]
    facade.messages.set_self_anchor(anchor_msg_id)

    # Bind ONLY attachment 1 to this anchor
    facade.attachments.bind_anchor(
        attachment_ids=[att_id1],
        anchor_msg_id=anchor_msg_id,
        user_uuid=user_uuid,
    )

    # Verify both exist in DB and point to the same physical path
    db_rec1 = facade.attachments.get_for_user(att_id1, user_uuid)
    db_rec2 = facade.attachments.get_for_user(att_id2, user_uuid)
    assert db_rec1 is not None
    assert db_rec2 is not None
    assert db_rec1["file_path"] == db_rec2["file_path"]
    physical_path = tmp_path / db_rec1["file_path"]
    assert physical_path.exists()

    # Delete the turn (which binds att_id1)
    r = client.delete(f"/messages/{anchor_msg_id}/turn", headers=headers)
    assert r.status_code == 204

    # Verify attachment 1 DB record is deleted
    assert facade.attachments.get_for_user(att_id1, user_uuid) is None
    # Verify attachment 2 DB record STILL exists
    assert facade.attachments.get_for_user(att_id2, user_uuid) is not None
    # Verify the physical file STILL exists (because att_id2 references it!)
    assert physical_path.exists()

    # Delete attachment 2 manually
    r = client.delete(f"/sessions/{sid}/attachments/{att_id2}", headers=headers)
    assert r.status_code == 204

    # Now the physical file should be deleted
    assert not physical_path.exists()


def test_get_attachment_success(isolated_api_env):
    client, facade, tmp_path = isolated_api_env
    token = register_and_login(client, "alice@example.com")
    user = facade.users.get_by_email("alice@example.com")
    user_uuid = user["uuid"]

    # Create project and session via API
    headers = {"Authorization": f"Bearer {token}"}
    r = client.post(f"/users/{user_uuid}/projects", json={"projectname": "p1"}, headers=headers)
    assert r.status_code == 201
    pid = r.json()["pid"]

    r = client.post(f"/projects/{pid}/sessions", json={"sessionname": "s1"}, headers=headers)
    assert r.status_code == 201
    sid = r.json()["sid"]

    # Upload attachment
    png_content = b"\x89PNG\r\n\x1a\nblahblah"
    file_payload = {"file": ("test.png", io.BytesIO(png_content), "image/png")}
    r = client.post(f"/sessions/{sid}/attachments", files=file_payload, headers=headers)
    assert r.status_code == 201
    data = r.json()
    attachment_id = data["attachment_id"]

    # Retrieve attachment
    r = client.get(f"/sessions/{sid}/attachments/{attachment_id}", headers=headers)
    assert r.status_code == 200
    assert r.content == png_content
    assert r.headers["content-type"] == "image/png"
    assert "attachment" in r.headers["content-disposition"]
    # The filename gets generated by the upload endpoint as "图片1.png"
    assert "filename*=utf-8''%E5%9B%BE%E7%89%871.png" in r.headers["content-disposition"]


def test_get_attachment_other_session_blocked(isolated_api_env):
    client, facade, tmp_path = isolated_api_env
    token = register_and_login(client, "alice@example.com")
    user = facade.users.get_by_email("alice@example.com")
    user_uuid = user["uuid"]

    headers = {"Authorization": f"Bearer {token}"}
    # Create project
    r = client.post(f"/users/{user_uuid}/projects", json={"projectname": "p1"}, headers=headers)
    pid = r.json()["pid"]

    # Create session 1
    r = client.post(f"/projects/{pid}/sessions", json={"sessionname": "s1"}, headers=headers)
    sid1 = r.json()["sid"]

    # Create session 2
    r = client.post(f"/projects/{pid}/sessions", json={"sessionname": "s2"}, headers=headers)
    sid2 = r.json()["sid"]

    # Upload to session 1
    png_content = b"\x89PNG\r\n\x1a\nblahblah"
    file_payload = {"file": ("test.png", io.BytesIO(png_content), "image/png")}
    r = client.post(f"/sessions/{sid1}/attachments", files=file_payload, headers=headers)
    attachment_id = r.json()["attachment_id"]

    # Try retrieving using session 2 ID
    r = client.get(f"/sessions/{sid2}/attachments/{attachment_id}", headers=headers)
    assert r.status_code == 404


def test_get_attachment_other_user_blocked(isolated_api_env):
    client, facade, tmp_path = isolated_api_env
    # User 1 registers & logins
    token1 = register_and_login(client, "alice@example.com")
    user1 = facade.users.get_by_email("alice@example.com")
    user_uuid1 = user1["uuid"]

    headers1 = {"Authorization": f"Bearer {token1}"}
    r = client.post(f"/users/{user_uuid1}/projects", json={"projectname": "p1"}, headers=headers1)
    pid = r.json()["pid"]

    r = client.post(f"/projects/{pid}/sessions", json={"sessionname": "s1"}, headers=headers1)
    sid = r.json()["sid"]

    png_content = b"\x89PNG\r\n\x1a\nblahblah"
    file_payload = {"file": ("test.png", io.BytesIO(png_content), "image/png")}
    r = client.post(f"/sessions/{sid}/attachments", files=file_payload, headers=headers1)
    attachment_id = r.json()["attachment_id"]

    # User 2 registers & logins
    token2 = register_and_login(client, "bob@example.com", username="bob")
    headers2 = {"Authorization": f"Bearer {token2}"}

    # User 2 attempts to download User 1's attachment
    r = client.get(f"/sessions/{sid}/attachments/{attachment_id}", headers=headers2)
    assert r.status_code == 404


def test_get_attachment_not_found(isolated_api_env):
    client, facade, tmp_path = isolated_api_env
    token = register_and_login(client, "alice@example.com")
    user = facade.users.get_by_email("alice@example.com")
    user_uuid = user["uuid"]

    headers = {"Authorization": f"Bearer {token}"}
    r = client.post(f"/users/{user_uuid}/projects", json={"projectname": "p1"}, headers=headers)
    pid = r.json()["pid"]

    r = client.post(f"/projects/{pid}/sessions", json={"sessionname": "s1"}, headers=headers)
    sid = r.json()["sid"]

    # Non-existent attachment UUID
    r = client.get(f"/sessions/{sid}/attachments/some-random-id", headers=headers)
    assert r.status_code == 404


def test_get_attachment_session_not_found(isolated_api_env):
    client, facade, tmp_path = isolated_api_env
    token = register_and_login(client, "alice@example.com")
    headers = {"Authorization": f"Bearer {token}"}

    # Non-existent session UUID
    r = client.get(f"/sessions/some-random-id/attachments/some-random-id", headers=headers)
    assert r.status_code == 404


def test_get_attachment_physical_file_missing(isolated_api_env):
    client, facade, tmp_path = isolated_api_env
    token = register_and_login(client, "alice@example.com")
    user = facade.users.get_by_email("alice@example.com")
    user_uuid = user["uuid"]

    headers = {"Authorization": f"Bearer {token}"}
    r = client.post(f"/users/{user_uuid}/projects", json={"projectname": "p1"}, headers=headers)
    pid = r.json()["pid"]

    r = client.post(f"/projects/{pid}/sessions", json={"sessionname": "s1"}, headers=headers)
    sid = r.json()["sid"]

    # Upload attachment
    png_content = b"\x89PNG\r\n\x1a\nblahblah"
    file_payload = {"file": ("test.png", io.BytesIO(png_content), "image/png")}
    r = client.post(f"/sessions/{sid}/attachments", files=file_payload, headers=headers)
    assert r.status_code == 201
    data = r.json()
    attachment_id = data["attachment_id"]

    # Find physical path
    db_record = facade.attachments.get_for_user(attachment_id, user_uuid)
    assert db_record is not None
    physical_path = tmp_path / db_record["file_path"]
    assert physical_path.exists()

    # Delete physical file from disk
    physical_path.unlink()
    assert not physical_path.exists()

    # Attempt retrieve attachment
    r = client.get(f"/sessions/{sid}/attachments/{attachment_id}", headers=headers)
    assert r.status_code == 404



