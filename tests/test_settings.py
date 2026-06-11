
"""Settings module tests: account, preferences, user_instruction."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from tests.conftest import auth_headers


@pytest.fixture
def settings_app(tmp_path, monkeypatch):
    db_path = tmp_path / 'test.db'
    data_dir = tmp_path / 'data'
    data_dir.mkdir()
    skills_dir = data_dir / 'skills'
    skills_dir.mkdir()

    monkeypatch.setattr('backend.config.BASE_DIR', tmp_path)
    monkeypatch.setattr('backend.config.DATABASE_PATH', str(db_path))
    monkeypatch.setattr('backend.config.SKILL_STORAGE_DIR', str(skills_dir))
    monkeypatch.setattr('backend.config.JWT_SECRET', 'test-secret')
    monkeypatch.setattr('backend.auth.JWT_SECRET', 'test-secret')
    monkeypatch.setattr('backend.file.BASE_DIR', tmp_path)

    from backend.db import DatabaseFacade
    from backend.db_dep import get_db
    from backend.auth import router as auth_router
    from backend.settings import router as settings_router
    from fastapi import FastAPI

    facade = DatabaseFacade(db_path=str(db_path))
    facade.setup_database()

    app = FastAPI()
    app.state.facade = facade
    app.dependency_overrides[get_db] = lambda: facade
    app.include_router(auth_router)
    app.include_router(settings_router)

    return app, facade


@pytest.fixture
def sclient(settings_app):
    app, _facade = settings_app
    with TestClient(app) as c:
        yield c


def _reg(client, email='user@test.com', username='testuser', password='password123'):
    from backend.auth import hash_password

    facade = client.app.state.facade
    if facade.users.get_by_email(email) is None:
        facade.users.create(username=username, email=email, password_hash=hash_password(password))
    r = client.post('/auth/login', json={'email': email, 'password': password})
    assert r.status_code == 200
    return r.json()['access_token']


class TestAccountInfo:
    def test_get_account_info(self, sclient):
        token = _reg(sclient)
        r = sclient.get('/settings/account', headers=auth_headers(token))
        assert r.status_code == 200
        data = r.json()
        assert data['username'] == 'testuser'
        assert data['email'] == 'user@test.com'

    def test_unauthenticated(self, sclient):
        r = sclient.get('/settings/account')
        assert r.status_code == 401


class TestUpdateUsername:
    def test_update_username(self, sclient):
        token = _reg(sclient)
        r = sclient.patch('/settings/account/username', headers=auth_headers(token), json={'username': 'newname'})
        assert r.status_code == 200
        assert r.json()['username'] == 'newname'

    def test_update_username_empty_rejected(self, sclient):
        token = _reg(sclient)
        r = sclient.patch('/settings/account/username', headers=auth_headers(token), json={'username': ''})
        assert r.status_code == 422


class TestChangePassword:
    def test_change_password_success(self, sclient):
        token = _reg(sclient)
        r = sclient.post('/settings/account/change-password', headers=auth_headers(token), json={
            'current_password': 'password123',
            'new_password': 'newpass456',
        })
        assert r.status_code == 204

        r2 = sclient.post('/auth/login', json={'email': 'user@test.com', 'password': 'newpass456'})
        assert r2.status_code == 200

    def test_change_password_wrong_current(self, sclient):
        token = _reg(sclient)
        r = sclient.post('/settings/account/change-password', headers=auth_headers(token), json={
            'current_password': 'wrongpassword',
            'new_password': 'newpass456',
        })
        assert r.status_code == 400
        assert r.json()['detail']['code'] == 'INVALID_PASSWORD'

    def test_change_password_clears_refresh_cookie(self, sclient):
        token = _reg(sclient)
        r = sclient.post('/settings/account/change-password', headers=auth_headers(token), json={
            'current_password': 'password123',
            'new_password': 'newpass456',
        })
        assert r.status_code == 204
        # Verify refresh cookie is cleared via Set-Cookie header
        set_cookie_header = r.headers.get('set-cookie', '')
        assert 'refresh_token' in set_cookie_header or 'Max-Age=0' in set_cookie_header


class TestPreferences:
    def test_default_preferences(self, sclient):
        token = _reg(sclient)
        r = sclient.get('/settings/preferences', headers=auth_headers(token))
        assert r.status_code == 200
        data = r.json()
        assert data['enter_mode'] == 'enter'
        assert data['updated_at'] is None

    def test_update_enter_mode(self, sclient):
        token = _reg(sclient)
        r = sclient.patch('/settings/preferences', headers=auth_headers(token), json={'enter_mode': 'ctrl_enter'})
        assert r.status_code == 200
        assert r.json()['enter_mode'] == 'ctrl_enter'
        assert r.json()['updated_at'] is not None

    def test_invalid_enter_mode(self, sclient):
        token = _reg(sclient)
        r = sclient.patch('/settings/preferences', headers=auth_headers(token), json={'enter_mode': 'invalid'})
        assert r.status_code == 422


class TestModelConfigUserInstruction:
    def test_create_with_instruction(self, sclient):
        token = _reg(sclient)
        r = sclient.post('/settings/model-configs', headers=auth_headers(token), json={
            'config_name': 'Test',
            'user_instruction': 'Answer in Chinese',
        })
        assert r.status_code == 201
        assert r.json()['user_instruction'] == 'Answer in Chinese'

    def test_update_instruction(self, sclient):
        token = _reg(sclient)
        create_r = sclient.post('/settings/model-configs', headers=auth_headers(token), json={
            'config_name': 'Test', 'user_instruction': 'Old',
        })
        cid = create_r.json()['config_id']
        r = sclient.patch(f'/settings/model-configs/{cid}', headers=auth_headers(token), json={
            'user_instruction': 'New',
        })
        assert r.status_code == 200
        assert r.json()['user_instruction'] == 'New'

    def test_default_empty(self, sclient):
        token = _reg(sclient)
        r = sclient.post('/settings/model-configs', headers=auth_headers(token), json={'config_name': 'NoInst'})
        assert r.json()['user_instruction'] == ''


class TestModelConfigActivationRules:
    def _create_config(self, client, token, name: str, *, supports_vision: bool = False, is_active: bool = False):
        r = client.post('/settings/model-configs', headers=auth_headers(token), json={
            'config_name': name,
            'model_name': name,
            'supports_vision': supports_vision,
            'is_active': is_active,
        })
        assert r.status_code == 201, r.text
        return r.json()

    def test_second_active_model_must_be_vision(self, sclient):
        token = _reg(sclient)
        text_a = self._create_config(sclient, token, 'text-a')
        text_b = self._create_config(sclient, token, 'text-b')
        vision = self._create_config(sclient, token, 'vision-a', supports_vision=True)

        r = sclient.post(f"/settings/model-configs/{text_a['config_id']}/activate", headers=auth_headers(token))
        assert r.status_code == 200
        assert r.json()['is_active'] is True

        r = sclient.post(f"/settings/model-configs/{text_b['config_id']}/activate", headers=auth_headers(token))
        assert r.status_code == 400
        assert r.json()['detail']['code'] == 'ACTIVE_MODEL_REQUIRES_VISION'

        r = sclient.post(f"/settings/model-configs/{vision['config_id']}/activate", headers=auth_headers(token))
        assert r.status_code == 200
        assert r.json()['is_active'] is True

        r = sclient.post(f"/settings/model-configs/{text_b['config_id']}/activate", headers=auth_headers(token))
        assert r.status_code == 400
        assert r.json()['detail']['code'] == 'ACTIVE_MODEL_LIMIT'

        r = sclient.post(f"/settings/model-configs/{text_a['config_id']}/activate", headers=auth_headers(token))
        assert r.status_code == 200
        assert r.json()['is_active'] is False

        r = sclient.post(f"/settings/model-configs/{text_b['config_id']}/activate", headers=auth_headers(token))
        assert r.status_code == 200
        assert r.json()['is_active'] is True

        r = sclient.get('/settings/model-configs/active', headers=auth_headers(token))
        assert r.status_code == 200
        data = r.json()
        assert len(data['configs']) == 2
        assert data['config']['config_id'] == text_b['config_id']
        assert {c['config_id'] for c in data['configs']} == {text_b['config_id'], vision['config_id']}

    def test_create_active_pair_rejects_two_text_models(self, sclient):
        token = _reg(sclient)
        self._create_config(sclient, token, 'text-a', is_active=True)

        r = sclient.post('/settings/model-configs', headers=auth_headers(token), json={
            'config_name': 'text-b',
            'supports_vision': False,
            'is_active': True,
        })
        assert r.status_code == 400
        assert r.json()['detail']['code'] == 'ACTIVE_MODEL_REQUIRES_VISION'

        vision = self._create_config(sclient, token, 'vision-a', supports_vision=True, is_active=True)
        assert vision['is_active'] is True

    def test_active_vision_mark_cannot_be_removed_from_pair(self, sclient):
        token = _reg(sclient)
        text = self._create_config(sclient, token, 'text-a')
        vision = self._create_config(sclient, token, 'vision-a', supports_vision=True)
        sclient.post(f"/settings/model-configs/{text['config_id']}/activate", headers=auth_headers(token))
        sclient.post(f"/settings/model-configs/{vision['config_id']}/activate", headers=auth_headers(token))

        r = sclient.patch(f"/settings/model-configs/{vision['config_id']}", headers=auth_headers(token), json={
            'supports_vision': False,
        })
        assert r.status_code == 400
        assert r.json()['detail']['code'] == 'ACTIVE_MODEL_REQUIRES_VISION'


class TestFetchModels:
    """POST /settings/model-configs/fetch-models 端点测试。"""

    def test_unauthenticated(self, sclient):
        r = sclient.post('/settings/model-configs/fetch-models', json={
            'api_key': 'sk-test', 'base_url': 'https://api.openai.com/v1',
        })
        assert r.status_code == 401

    def test_invalid_base_url_ssrf(self, sclient):
        token = _reg(sclient)
        r = sclient.post('/settings/model-configs/fetch-models', headers=auth_headers(token), json={
            'api_key': 'sk-test', 'base_url': 'http://127.0.0.1/v1',
        })
        assert r.status_code == 422

    def test_empty_api_key_returns_failure(self, sclient, monkeypatch):
        """空 api_key 时 GetProvider 抛出 RuntimeError，端点应返回 success=false。"""
        token = _reg(sclient)
        # 确保 env 默认 api_key 也为空
        monkeypatch.setattr('backend.config.model.MODEL_PROVIDER_API_KEY', '')
        r = sclient.post('/settings/model-configs/fetch-models', headers=auth_headers(token), json={
            'api_key': '', 'base_url': 'https://api.openai.com/v1',
        })
        assert r.status_code == 200
        data = r.json()
        assert data['success'] is False
        assert 'API key' in data['message'] or 'Missing' in data['message']

    def test_successful_fetch(self, sclient, monkeypatch):
        """模拟 OpenAI client.models.list() 返回模型列表。"""
        from unittest.mock import AsyncMock, MagicMock

        mock_model_1 = MagicMock()
        mock_model_1.id = 'gpt-4o'
        mock_model_2 = MagicMock()
        mock_model_2.id = 'gpt-4o-mini'

        mock_response = MagicMock()
        mock_response.data = [mock_model_1, mock_model_2]

        mock_client = MagicMock()
        mock_client.models = MagicMock()
        mock_client.models.list = AsyncMock(return_value=mock_response)

        mock_openai_chat_model = MagicMock()
        mock_openai_chat_model.client = mock_client

        def mock_get_provider(*, api_key, base_url, model_name):
            return mock_openai_chat_model

        monkeypatch.setattr('backend.config.model.GetProvider', mock_get_provider)

        token = _reg(sclient)
        r = sclient.post('/settings/model-configs/fetch-models', headers=auth_headers(token), json={
            'api_key': 'sk-test', 'base_url': 'https://api.openai.com/v1',
        })
        assert r.status_code == 200
        data = r.json()
        assert data['success'] is True
        assert data['models'] == ['gpt-4o', 'gpt-4o-mini']
        assert data['message'] == ''

    def test_provider_not_support_models_endpoint(self, sclient, monkeypatch):
        """模拟 NotFoundError（提供商不支持 /models）。"""
        from openai import NotFoundError
        from unittest.mock import AsyncMock, MagicMock

        mock_client = MagicMock()
        mock_client.models = MagicMock()
        mock_client.models.list = AsyncMock(
            side_effect=NotFoundError(message='Not found', response=MagicMock(status_code=404), body=None)
        )

        mock_openai_chat_model = MagicMock()
        mock_openai_chat_model.client = mock_client

        def mock_get_provider(*, api_key, base_url, model_name):
            return mock_openai_chat_model

        monkeypatch.setattr('backend.config.model.GetProvider', mock_get_provider)

        token = _reg(sclient)
        r = sclient.post('/settings/model-configs/fetch-models', headers=auth_headers(token), json={
            'api_key': 'sk-test', 'base_url': 'https://api.example.com/v1',
        })
        assert r.status_code == 200
        data = r.json()
        assert data['success'] is False
        assert '不支持' in data['message']

    def test_invalid_api_key(self, sclient, monkeypatch):
        """模拟 AuthenticationError（API Key 无效）。"""
        from openai import AuthenticationError
        from unittest.mock import AsyncMock, MagicMock

        mock_client = MagicMock()
        mock_client.models = MagicMock()
        mock_client.models.list = AsyncMock(
            side_effect=AuthenticationError(message='Invalid API key', response=MagicMock(status_code=401), body=None)
        )

        mock_openai_chat_model = MagicMock()
        mock_openai_chat_model.client = mock_client

        def mock_get_provider(*, api_key, base_url, model_name):
            return mock_openai_chat_model

        monkeypatch.setattr('backend.config.model.GetProvider', mock_get_provider)

        token = _reg(sclient)
        r = sclient.post('/settings/model-configs/fetch-models', headers=auth_headers(token), json={
            'api_key': 'sk-invalid', 'base_url': 'https://api.openai.com/v1',
        })
        assert r.status_code == 200
        data = r.json()
        assert data['success'] is False
        assert 'API Key' in data['message']
