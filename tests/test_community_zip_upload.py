from __future__ import annotations

import uuid
import zipfile
import time
from io import BytesIO
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

import backend.auth as auth_module
import backend.data as data_module
import backend.transfer as transfer_module
from backend.db import DatabaseFacade


def _zip_bytes(entries: dict[str, str]) -> bytes:
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path, content in entries.items():
            archive.writestr(path, content)
    return buffer.getvalue()


def _skill_zip(name: str = "zip-skill") -> bytes:
    return _zip_bytes({
        f"{name}/SKILL.md": f"---\nname: {name}\ndescription: Uploaded from zip\n---\n\n# {name}\n",
        f"{name}/references/notes.md": "reference\n",
    })


def _auth_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "X-Nonce": str(uuid.uuid4()),
        "X-Nonce-Timestamp": str(time.time()),
        "Content-Type": "application/zip",
    }


def _client(tmp_path: Path, monkeypatch) -> tuple[TestClient, DatabaseFacade, str]:
    db = DatabaseFacade(db_path=str(tmp_path / "test.db"))
    db.setup_database()
    user = db.users.create(
        username="Zip User",
        email=f"{uuid.uuid4()}@example.com",
        password_hash="unused",
    )

    monkeypatch.setattr(auth_module, "db", db)
    monkeypatch.setattr(data_module, "db", db)
    monkeypatch.setattr(transfer_module, "db", db)
    monkeypatch.setattr(transfer_module, "BASE_DIR", tmp_path)

    app = FastAPI()
    app.include_router(data_module.router)
    return TestClient(app), db, auth_module.create_access_token(user["uuid"])


def test_upload_community_skill_zip_publishes_archive(tmp_path: Path, monkeypatch) -> None:
    client, _db, token = _client(tmp_path, monkeypatch)

    response = client.post(
        "/community/skills/upload",
        content=_skill_zip(),
        headers=_auth_headers(token),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "zip-skill"
    assert body["display_name"] is None
    assert body["description"] == "Uploaded from zip"
    assert body["size_bytes"] > 0
    assert (tmp_path / "archived_skill" / body["id"] / "SKILL.md").is_file()
    assert (tmp_path / "archived_skill" / body["id"] / "references" / "notes.md").is_file()


def test_upload_community_skill_zip_accepts_reference_alias(tmp_path: Path, monkeypatch) -> None:
    client, _db, token = _client(tmp_path, monkeypatch)
    zip_body = _zip_bytes({
        "alias-skill/SKILL.md": "---\nname: alias-skill\ndescription: Uses reference alias\n---\n",
        "alias-skill/reference/guide.md": "guide\n",
    })

    response = client.post(
        "/community/skills/upload",
        content=zip_body,
        headers=_auth_headers(token),
    )

    assert response.status_code == 201
    body = response.json()
    assert (tmp_path / "archived_skill" / body["id"] / "references" / "guide.md").is_file()
    assert not (tmp_path / "archived_skill" / body["id"] / "reference").exists()


def test_upload_community_skill_zip_uses_frontmatter_name_not_folder_name(
    tmp_path: Path,
    monkeypatch,
) -> None:
    client, _db, token = _client(tmp_path, monkeypatch)
    zip_body = _zip_bytes({
        "wrong-folder/SKILL.md": "---\nname: canonical-skill\ndescription: Uses frontmatter name\n---\n",
        "wrong-folder/reference/guide.md": "guide\n",
    })

    response = client.post(
        "/community/skills/upload",
        content=zip_body,
        headers=_auth_headers(token),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "canonical-skill"
    assert (tmp_path / "archived_skill" / body["id"] / "SKILL.md").is_file()
    assert (tmp_path / "archived_skill" / body["id"] / "references" / "guide.md").is_file()
    assert not (tmp_path / "archived_skill" / body["id"] / "wrong-folder").exists()


def test_upload_community_skill_zip_preserves_display_name(tmp_path: Path, monkeypatch) -> None:
    client, db, token = _client(tmp_path, monkeypatch)
    zip_body = _zip_bytes({
        "display-skill/SKILL.md": (
            "---\n"
            "name: display-skill\n"
            "display_name: 中文展示名\n"
            "description: Has display name\n"
            "---\n"
        ),
    })

    response = client.post(
        "/community/skills/upload",
        content=zip_body,
        headers=_auth_headers(token),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "display-skill"
    assert body["display_name"] == "中文展示名"
    assert db.community.get_by_id(body["id"])["display_name"] == "中文展示名"


def test_upload_community_skill_zip_requires_auth(tmp_path: Path, monkeypatch) -> None:
    client, _db, _token = _client(tmp_path, monkeypatch)

    response = client.post(
        "/community/skills/upload",
        content=_skill_zip(),
        headers={"Content-Type": "application/zip"},
    )

    assert response.status_code == 401


def test_upload_community_skill_zip_rejects_non_zip(tmp_path: Path, monkeypatch) -> None:
    client, _db, token = _client(tmp_path, monkeypatch)

    response = client.post(
        "/community/skills/upload",
        content=b"not a zip",
        headers=_auth_headers(token),
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "ZIP_VALIDATION_ERROR"


def test_upload_community_skill_zip_accepts_examples_and_templates(tmp_path: Path, monkeypatch) -> None:
    client, _db, token = _client(tmp_path, monkeypatch)
    zip_body = _zip_bytes({
        "new-skill/SKILL.md": "---\nname: new-skill\ndescription: Uses examples and templates\n---\n",
        "new-skill/examples/test.txt": "example txt\n",
        "new-skill/templates/layout.json": "{}",
    })

    response = client.post(
        "/community/skills/upload",
        content=zip_body,
        headers=_auth_headers(token),
    )

    assert response.status_code == 201
    body = response.json()
    assert (tmp_path / "archived_skill" / body["id"] / "examples" / "test.txt").is_file()
    assert (tmp_path / "archived_skill" / body["id"] / "templates" / "layout.json").is_file()


def test_upload_community_skill_zip_accepts_singular_aliases(tmp_path: Path, monkeypatch) -> None:
    client, _db, token = _client(tmp_path, monkeypatch)
    zip_body = _zip_bytes({
        "alias-skill/SKILL.md": "---\nname: alias-skill\ndescription: Uses singular aliases\n---\n",
        "alias-skill/example/test.txt": "example txt\n",
        "alias-skill/template/layout.json": "{}",
    })

    response = client.post(
        "/community/skills/upload",
        content=zip_body,
        headers=_auth_headers(token),
    )

    assert response.status_code == 201
    body = response.json()
    assert (tmp_path / "archived_skill" / body["id"] / "examples" / "test.txt").is_file()
    assert (tmp_path / "archived_skill" / body["id"] / "templates" / "layout.json").is_file()
    assert not (tmp_path / "archived_skill" / body["id"] / "example").exists()
    assert not (tmp_path / "archived_skill" / body["id"] / "template").exists()

