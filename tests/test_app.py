"""
Testes unitários do flag-service.

Estratégia: mockamos psycopg2 e requests para isolar completamente
a lógica de negócio sem necessidade de banco de dados ou auth-service.
"""
import json
import pytest
from unittest.mock import patch, MagicMock


# ── Fixtures para isolar a inicialização do módulo ─────────────────────────

@pytest.fixture(autouse=True)
def mock_env(monkeypatch):
    """Define variáveis de ambiente obrigatórias antes de importar o módulo."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://fake:fake@localhost/fake")
    monkeypatch.setenv("AUTH_SERVICE_URL", "http://fake-auth")


@pytest.fixture
def app_client(mock_env):
    """
    Cria o cliente de teste do Flask com dependências externas mockadas.
    O pool de conexão e o auth-service são substituídos por mocks.
    """
    with patch("psycopg2.pool.SimpleConnectionPool") as mock_pool_cls, \
         patch("requests.get") as mock_requests_get:

        # Configura o mock do pool
        mock_pool = MagicMock()
        mock_pool_cls.return_value = mock_pool

        # Importa APÓS os patches para evitar sys.exit(1)
        import importlib
        import sys
        if "app" in sys.modules:
            del sys.modules["app"]

        import app as flask_app_module
        flask_app_module.pool = mock_pool

        flask_app_module.app.config["TESTING"] = True
        client = flask_app_module.app.test_client()

        yield client, mock_pool, mock_requests_get, flask_app_module


# ── Helper: simula autenticação bem-sucedida ───────────────────────────────

def auth_ok(mock_requests_get):
    """Configura o mock do auth-service para retornar 200."""
    resp = MagicMock()
    resp.status_code = 200
    mock_requests_get.return_value = resp


def auth_fail(mock_requests_get):
    """Configura o mock do auth-service para retornar 401."""
    resp = MagicMock()
    resp.status_code = 401
    mock_requests_get.return_value = resp


# ── /health ────────────────────────────────────────────────────────────────

class TestHealth:
    def test_health_returns_ok(self, app_client):
        client, *_ = app_client
        res = client.get("/health")
        assert res.status_code == 200
        assert res.get_json() == {"status": "ok"}


# ── Middleware de autenticação ─────────────────────────────────────────────

class TestAuthMiddleware:
    def test_missing_auth_header_returns_401(self, app_client):
        client, mock_pool, mock_requests_get, _ = app_client
        res = client.get("/flags")
        assert res.status_code == 401

    def test_invalid_key_returns_401(self, app_client):
        client, mock_pool, mock_requests_get, _ = app_client
        auth_fail(mock_requests_get)
        res = client.get("/flags", headers={"Authorization": "Bearer invalid_key"})
        assert res.status_code == 401

    def test_auth_service_timeout_returns_504(self, app_client):
        import requests as req_lib
        client, mock_pool, mock_requests_get, _ = app_client
        mock_requests_get.side_effect = req_lib.exceptions.Timeout
        res = client.get("/flags", headers={"Authorization": "Bearer somekey"})
        assert res.status_code == 504

    def test_auth_service_unavailable_returns_503(self, app_client):
        import requests as req_lib
        client, mock_pool, mock_requests_get, _ = app_client
        mock_requests_get.side_effect = req_lib.exceptions.ConnectionError
        res = client.get("/flags", headers={"Authorization": "Bearer somekey"})
        assert res.status_code == 503


# ── POST /flags ────────────────────────────────────────────────────────────

class TestCreateFlag:
    def test_create_flag_success(self, app_client):
        client, mock_pool, mock_requests_get, flask_app_module = app_client
        auth_ok(mock_requests_get)

        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_pool.getconn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cur
        mock_cur.fetchone.return_value = {
            "id": 1, "name": "my-flag",
            "description": "desc", "is_enabled": False
        }

        res = client.post(
            "/flags",
            data=json.dumps({"name": "my-flag", "description": "desc"}),
            content_type="application/json",
            headers={"Authorization": "Bearer valid_key"},
        )
        assert res.status_code == 201
        data = res.get_json()
        assert data["name"] == "my-flag"

    def test_create_flag_missing_name_returns_400(self, app_client):
        client, mock_pool, mock_requests_get, _ = app_client
        auth_ok(mock_requests_get)

        res = client.post(
            "/flags",
            data=json.dumps({"description": "no name"}),
            content_type="application/json",
            headers={"Authorization": "Bearer valid_key"},
        )
        assert res.status_code == 400

    def test_create_flag_duplicate_returns_409(self, app_client):
        import psycopg2
        client, mock_pool, mock_requests_get, _ = app_client
        auth_ok(mock_requests_get)

        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_pool.getconn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cur
        mock_cur.execute.side_effect = psycopg2.IntegrityError

        res = client.post(
            "/flags",
            data=json.dumps({"name": "dup-flag"}),
            content_type="application/json",
            headers={"Authorization": "Bearer valid_key"},
        )
        assert res.status_code == 409

    def test_create_flag_db_error_returns_500(self, app_client):
        client, mock_pool, mock_requests_get, _ = app_client
        auth_ok(mock_requests_get)

        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_pool.getconn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cur
        mock_cur.execute.side_effect = Exception("db error")

        res = client.post(
            "/flags",
            data=json.dumps({"name": "error-flag"}),
            content_type="application/json",
            headers={"Authorization": "Bearer valid_key"},
        )
        assert res.status_code == 500


# ── GET /flags ─────────────────────────────────────────────────────────────

class TestGetFlags:
    def test_list_flags_returns_200(self, app_client):
        client, mock_pool, mock_requests_get, _ = app_client
        auth_ok(mock_requests_get)

        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_pool.getconn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cur
        mock_cur.fetchall.return_value = [
            {"id": 1, "name": "flag-a", "is_enabled": True}
        ]

        res = client.get("/flags", headers={"Authorization": "Bearer valid_key"})
        assert res.status_code == 200
        assert isinstance(res.get_json(), list)

    def test_list_flags_db_error_returns_500(self, app_client):
        client, mock_pool, mock_requests_get, _ = app_client
        auth_ok(mock_requests_get)

        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_pool.getconn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cur
        mock_cur.execute.side_effect = Exception("db error")

        res = client.get("/flags", headers={"Authorization": "Bearer valid_key"})
        assert res.status_code == 500


# ── GET /flags/<name> ──────────────────────────────────────────────────────

class TestGetFlag:
    def test_get_existing_flag_returns_200(self, app_client):
        client, mock_pool, mock_requests_get, _ = app_client
        auth_ok(mock_requests_get)

        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_pool.getconn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cur
        mock_cur.fetchone.return_value = {
            "id": 1, "name": "existing-flag", "is_enabled": True
        }

        res = client.get(
            "/flags/existing-flag",
            headers={"Authorization": "Bearer valid_key"}
        )
        assert res.status_code == 200
        assert res.get_json()["name"] == "existing-flag"

    def test_get_nonexistent_flag_returns_404(self, app_client):
        client, mock_pool, mock_requests_get, _ = app_client
        auth_ok(mock_requests_get)

        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_pool.getconn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cur
        mock_cur.fetchone.return_value = None

        res = client.get(
            "/flags/nonexistent",
            headers={"Authorization": "Bearer valid_key"}
        )
        assert res.status_code == 404


# ── PUT /flags/<name> ──────────────────────────────────────────────────────

class TestUpdateFlag:
    def test_update_flag_success(self, app_client):
        client, mock_pool, mock_requests_get, _ = app_client
        auth_ok(mock_requests_get)

        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_pool.getconn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cur
        mock_cur.rowcount = 1
        mock_cur.fetchone.return_value = {
            "id": 1, "name": "my-flag", "is_enabled": True
        }

        res = client.put(
            "/flags/my-flag",
            data=json.dumps({"is_enabled": True}),
            content_type="application/json",
            headers={"Authorization": "Bearer valid_key"},
        )
        assert res.status_code == 200

    def test_update_flag_no_body_returns_400(self, app_client):
        client, mock_pool, mock_requests_get, _ = app_client
        auth_ok(mock_requests_get)

        res = client.put(
            "/flags/my-flag",
            content_type="application/json",
            headers={"Authorization": "Bearer valid_key"},
        )
        assert res.status_code == 400

    def test_update_flag_no_valid_fields_returns_400(self, app_client):
        client, mock_pool, mock_requests_get, _ = app_client
        auth_ok(mock_requests_get)

        res = client.put(
            "/flags/my-flag",
            data=json.dumps({"unknown_field": "value"}),
            content_type="application/json",
            headers={"Authorization": "Bearer valid_key"},
        )
        assert res.status_code == 400

    def test_update_nonexistent_flag_returns_404(self, app_client):
        client, mock_pool, mock_requests_get, _ = app_client
        auth_ok(mock_requests_get)

        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_pool.getconn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cur
        mock_cur.rowcount = 0

        res = client.put(
            "/flags/ghost",
            data=json.dumps({"is_enabled": True}),
            content_type="application/json",
            headers={"Authorization": "Bearer valid_key"},
        )
        assert res.status_code == 404


# ── DELETE /flags/<name> ───────────────────────────────────────────────────

class TestDeleteFlag:
    def test_delete_existing_flag_returns_204(self, app_client):
        client, mock_pool, mock_requests_get, _ = app_client
        auth_ok(mock_requests_get)

        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_pool.getconn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cur
        mock_cur.rowcount = 1

        res = client.delete(
            "/flags/my-flag",
            headers={"Authorization": "Bearer valid_key"}
        )
        assert res.status_code == 204

    def test_delete_nonexistent_flag_returns_404(self, app_client):
        client, mock_pool, mock_requests_get, _ = app_client
        auth_ok(mock_requests_get)

        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_pool.getconn.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cur
        mock_cur.rowcount = 0

        res = client.delete(
            "/flags/ghost",
            headers={"Authorization": "Bearer valid_key"}
        )
        assert res.status_code == 404
