from fastapi.testclient import TestClient

from askdb.main import create_app

PASSWORD = "correct horse battery"


def login(client: TestClient, username: str, password: str = PASSWORD):
    return client.post("/api/auth/login", json={"username": username, "password": password})


def test_protected_routes_require_a_session(config_dir):
    with TestClient(create_app(config_dir)) as client:
        assert client.get("/api/databases").status_code == 401
        assert client.get("/api/auth/me").status_code == 401


def test_wrong_password_is_rejected(config_dir, add_user):
    add_user("ana", role="support")
    with TestClient(create_app(config_dir)) as client:
        assert login(client, "ana", "wrong password!").status_code == 401
        assert client.get("/api/databases").status_code == 401


def test_login_sets_session_and_logout_ends_it(config_dir, add_user):
    add_user("ana", role="support")
    with TestClient(create_app(config_dir)) as client:
        response = login(client, "ana")
        assert response.status_code == 200
        assert response.json() == {"id": 1, "username": "ana", "role": "support"}
        assert client.get("/api/auth/me").json()["username"] == "ana"
        assert client.get("/api/databases").status_code == 200

        assert client.post("/api/auth/logout").status_code == 204
        assert client.get("/api/auth/me").status_code == 401


def test_analyst_cannot_create_users(config_dir, add_user):
    add_user("ana", role="analyst")
    with TestClient(create_app(config_dir)) as client:
        login(client, "ana")
        response = client.post(
            "/api/admin/users",
            json={"username": "bo", "password": "another-long-pass", "role": "analyst"},
        )
        assert response.status_code == 403


def test_support_creates_user_and_duplicate_is_refused(config_dir, add_user):
    add_user("sam", role="support")
    with TestClient(create_app(config_dir)) as client:
        login(client, "sam")
        body = {"username": "bo", "password": "another-long-pass", "role": "analyst"}
        assert client.post("/api/admin/users", json=body).status_code == 201
        assert client.post("/api/admin/users", json=body).status_code == 409

        assert login(client, "bo", "another-long-pass").status_code == 200


def test_password_reset_replaces_password_and_ends_sessions(config_dir, add_user):
    add_user("sam", role="support")
    add_user("ana", role="analyst")
    with TestClient(create_app(config_dir)) as support:
        login(support, "sam")
        with TestClient(create_app(config_dir)) as analyst:
            login(analyst, "ana")
            assert analyst.get("/api/auth/me").status_code == 200

            reset = support.post(
                "/api/admin/users/2/password", json={"password": "a-brand-new-pass"}
            )
            assert reset.status_code == 204

            # The analyst's existing session is gone.
            assert analyst.get("/api/auth/me").status_code == 401

    with TestClient(create_app(config_dir)) as client:
        assert login(client, "ana", PASSWORD).status_code == 401
        assert login(client, "ana", "a-brand-new-pass").status_code == 200


def test_reset_for_unknown_user_is_404(config_dir, add_user):
    add_user("sam", role="support")
    with TestClient(create_app(config_dir)) as client:
        login(client, "sam")
        response = client.post("/api/admin/users/999/password", json={"password": "a-brand-new-pass"})
        assert response.status_code == 404
