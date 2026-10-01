import os
import tempfile
from unittest.mock import Mock, patch

import pytest
from unittest.mock import patch

from app import create_app
from app.services import clean_generated_text, generate_article


@pytest.fixture()
def client():
    database = os.path.join(tempfile.gettempdir(), "2gc-test.sqlite3")
    try:
        os.remove(database)
    except FileNotFoundError:
        pass
    app = create_app({"TESTING": True, "DATABASE_PATH": database})
    with app.test_client() as test_client:
        yield test_client


def create_article(client):
    return client.post(
        "/articles/new",
        data={
            "title": "Une actualité",
            "raw_content": "Une information importante.",
            "category_id": "1",
            "level": "basic",
            "language": "fr",
        },
        follow_redirects=False,
    )


def test_homepage_is_dynamic(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"Donnez une voix" in response.data
    assert b"Fonctionnalit" in response.data
    create_article(client)
    response = client.get("/dashboard")
    assert b"Une actualit" in response.data


def test_health_check_is_ready(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}


def test_shared_password_protects_editorial_pages(client):
    client.application.config["APP_ACCESS_PASSWORD"] = "team-secret"
    assert client.get("/").status_code == 200
    assert client.get("/health").status_code == 200
    protected = client.get("/dashboard")
    assert protected.status_code == 302
    assert protected.headers["Location"].startswith("/login")
    api_response = client.post("/api/articles/1/generate")
    assert api_response.status_code == 401
    assert api_response.get_json()["error"] == "Connexion requise."
    login = client.post("/login", data={"password": "team-secret"})
    assert login.status_code == 302
    assert client.get("/dashboard").status_code == 200
    assert client.post("/logout").status_code == 302
    assert client.get("/dashboard").status_code == 302


def test_article_creation_and_detail(client):
    response = create_article(client)
    assert response.status_code == 302
    detail = client.get(response.headers["Location"])
    assert detail.status_code == 200
    assert b"Une actualit" in detail.data


def test_new_article_uses_category_and_creates_no_version(client):
    response = create_article(client)
    article_id = response.headers["Location"].rsplit("/", 1)[-1]
    with client.application.app_context():
        from app.db import get_db
        article = get_db().execute(
            "SELECT category_id FROM articles WHERE id = ?", (article_id,)
        ).fetchone()
        versions = get_db().execute(
            "SELECT COUNT(*) AS total FROM article_versions WHERE article_id = ?",
            (article_id,),
        ).fetchone()
    assert article["category_id"] == 1
    assert versions["total"] == 0


def test_missing_article_returns_404(client):
    assert client.get("/articles/9999").status_code == 404


def test_production_requires_secret_key(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("SECRET_KEY", raising=False)
    with patch("app.load_dotenv"):
        with pytest.raises(RuntimeError, match="SECRET_KEY"):
            create_app({"TESTING": True, "DATABASE_PATH": ":memory:"})


def test_article_creation_rejects_invalid_editorial_values(client):
    response = client.post(
        "/articles/new",
        data={
            "title": "Sujet",
            "raw_content": "Source",
            "category_id": "1",
            "level": "invalid",
            "language": "fr",
        },
    )
    assert response.status_code == 200
    assert b"param" in response.data


def test_generation_requires_openrouter_key(client):
    client.application.config["OPENROUTER_API_KEY"] = ""
    response = create_article(client)
    article_id = response.headers["Location"].rsplit("/", 1)[-1]
    response = client.post(f"/api/articles/{article_id}/generate")
    assert response.status_code == 502
    assert "Impossible de générer" in response.get_json()["error"]


def test_generation_sends_bearer_token(client):
    app = client.application
    app.config["OPENROUTER_API_KEY"] = "test-key"
    response = Mock(ok=True)
    response.json.return_value = {
        "choices": [{"message": {"content": "Article généré"}}]
    }
    with patch("app.services.requests.post", return_value=response) as post:
        with app.app_context():
            content = generate_article("Sujet", "Source", "basic", "Actualités", "fr")
    assert content == "Article généré"
    assert post.call_args.kwargs["headers"]["Authorization"] == "Bearer test-key"


def test_generated_text_removes_markdown_formatting():
    content = "# Titre\n\n**Introduction** avec `un formatage`.\n\n* Un élément"
    assert clean_generated_text(content) == "Titre\n\nIntroduction avec un formatage.\n\nUn élément"
