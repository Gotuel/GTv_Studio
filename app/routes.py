from datetime import datetime, timezone
import logging
from pathlib import Path

from flask import Blueprint, flash, jsonify, redirect, render_template, request, send_from_directory, url_for
from flask import current_app
import requests

from .db import get_db
from .services import generate_article, generate_audio

main = Blueprint("main", __name__)
logger = logging.getLogger(__name__)
MAX_TITLE_LENGTH = 200
MAX_SOURCE_LENGTH = 500
MAX_CONTENT_LENGTH = 100_000
ALLOWED_LEVELS = {"basic", "intermediate", "professional"}
ALLOWED_LANGUAGES = {"fr", "en"}


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@main.get("/")
def index():
    return render_template("index.html", landing=True)


@main.get("/dashboard")
def dashboard():
    db = get_db()
    stats = db.execute(
        """SELECT COUNT(*) total,
        SUM(status = 'draft') drafts, SUM(status = 'validated') validated,
        (SELECT COUNT(*) FROM audios WHERE status = 'ready') audios FROM articles"""
    ).fetchone()
    recent = db.execute(
        """SELECT articles.*, categories.name AS category
        FROM articles JOIN categories ON categories.id = articles.category_id
        ORDER BY articles.updated_at DESC LIMIT 5"""
    ).fetchall()
    return render_template("dashboard.html", stats=stats, recent=recent)


@main.route("/articles/new", methods=("GET", "POST"))
def new_article():
    if request.method == "POST":
        form = request.form
        title, raw = form.get("title", "").strip(), form.get("raw_content", "").strip()
        if not title or not raw:
            flash("Le titre et le contenu brut sont obligatoires.", "error")
            return render_template("new_article.html", form=form)
        if len(title) > MAX_TITLE_LENGTH or len(raw) > MAX_CONTENT_LENGTH:
            flash("Le titre ou le contenu dépasse la taille autorisée.", "error")
            return render_template("new_article.html", form=form)
        db = get_db()
        category_id = form.get("category_id", "").strip()
        level = form.get("level", "intermediate")
        language = form.get("language", "fr")
        source = form.get("source", "").strip()
        category = db.execute(
            "SELECT 1 FROM categories WHERE id = ? AND is_active = 1",
            (category_id,),
        ).fetchone()
        if not category_id.isdigit() or category is None:
            flash("Veuillez sélectionner une catégorie valide.", "error")
            categories = db.execute(
                "SELECT * FROM categories WHERE is_active = 1 ORDER BY name"
            ).fetchall()
            return render_template("new_article.html", form=form, categories=categories)
        if level not in ALLOWED_LEVELS or language not in ALLOWED_LANGUAGES:
            flash("Les paramètres de rédaction sélectionnés sont invalides.", "error")
            categories = db.execute(
                "SELECT * FROM categories WHERE is_active = 1 ORDER BY name"
            ).fetchall()
            return render_template("new_article.html", form=form, categories=categories)
        if len(source) > MAX_SOURCE_LENGTH:
            flash("La source est trop longue.", "error")
            categories = db.execute(
                "SELECT * FROM categories WHERE is_active = 1 ORDER BY name"
            ).fetchall()
            return render_template("new_article.html", form=form, categories=categories)
        cursor = db.execute(
            """INSERT INTO articles
            (title, raw_content, level, category_id, source, language, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (title, raw, level, int(category_id), source, language, now()),
        )
        db.commit()
        flash("Contenu sauvegardé comme brouillon.", "success")
        return redirect(url_for("main.article_detail", article_id=cursor.lastrowid))
    categories = get_db().execute(
        "SELECT * FROM categories WHERE is_active = 1 ORDER BY name"
    ).fetchall()
    return render_template("new_article.html", form={}, categories=categories)


@main.get("/articles")
def articles():
    query, status, category = request.args.get("q", ""), request.args.get("status", ""), request.args.get("category", "")
    sql = """SELECT articles.*, categories.name AS category
        FROM articles JOIN categories ON categories.id = articles.category_id
        WHERE (articles.title LIKE ? OR articles.raw_content LIKE ?)"""
    params = [f"%{query}%", f"%{query}%"]
    if status:
        sql += " AND articles.status = ?"; params.append(status)
    if category:
        sql += " AND articles.category_id = ?"; params.append(category)
    rows = get_db().execute(sql + " ORDER BY articles.updated_at DESC", params).fetchall()
    categories = get_db().execute(
        "SELECT * FROM categories WHERE is_active = 1 ORDER BY name"
    ).fetchall()
    return render_template("articles.html", articles=rows, categories=categories)


@main.get("/articles/<int:article_id>")
def article_detail(article_id):
    article = get_db().execute(
        """SELECT articles.*, categories.name AS category
        FROM articles JOIN categories ON categories.id = articles.category_id
        WHERE articles.id = ?""",
        (article_id,),
    ).fetchone()
    if article is None:
        return "Article introuvable", 404
    versions = get_db().execute(
        "SELECT * FROM article_versions WHERE article_id = ? ORDER BY version_number DESC",
        (article_id,),
    ).fetchall()
    audios = get_db().execute(
        "SELECT * FROM audios WHERE article_id = ? ORDER BY created_at DESC",
        (article_id,),
    ).fetchall()
    current_version = next((version for version in versions if version["is_current"]), None)
    return render_template(
        "article_detail.html",
        article=article,
        versions=versions,
        audios=audios,
        current_version=current_version,
    )


@main.post("/api/articles/<int:article_id>/generate")
def generate(article_id):
    db = get_db()
    article = db.execute("SELECT * FROM articles WHERE id = ?", (article_id,)).fetchone()
    if article is None:
        return jsonify(error="Article introuvable"), 404
    db.execute(
        "UPDATE articles SET status = 'generating', updated_at = ? WHERE id = ?",
        (now(), article_id),
    )
    db.commit()
    try:
        category = db.execute(
            "SELECT name FROM categories WHERE id = ?", (article["category_id"],)
        ).fetchone()
        content = generate_article(
            article["title"], article["raw_content"], article["level"],
            category["name"] if category else "Actualités", article["language"]
        )
    except (RuntimeError, requests.RequestException) as exc:
        logger.exception("Article generation failed for article_id=%s", article_id)
        db.execute(
            "UPDATE articles SET status = 'draft', updated_at = ? WHERE id = ?",
            (now(), article_id),
        )
        db.commit()
        return jsonify(error="Impossible de générer l'article pour le moment. Réessayez plus tard."), 502
    db.execute(
        "UPDATE article_versions SET is_current = 0 WHERE article_id = ?",
        (article_id,),
    )
    version_number = db.execute(
        "SELECT COALESCE(MAX(version_number), 0) + 1 AS next_number "
        "FROM article_versions WHERE article_id = ?",
        (article_id,),
    ).fetchone()["next_number"]
    db.execute(
        """INSERT INTO article_versions
        (article_id, version_number, content, version_type, is_current)
        VALUES (?, ?, ?, 'ai_generated', 1)""",
        (article_id, version_number, content),
    )
    db.execute(
        "UPDATE articles SET status = 'review', updated_at = ? WHERE id = ?",
        (now(), article_id),
    )
    db.commit()
    return jsonify(redirect=url_for("main.article_detail", article_id=article_id))


@main.post("/articles/<int:article_id>/save")
def save_article(article_id):
    content = request.form.get("final_content", "").strip()
    if not content:
        flash("Le contenu final ne peut pas être vide.", "error")
    else:
        db = get_db()
        db.execute(
            "UPDATE article_versions SET is_current = 0 WHERE article_id = ?",
            (article_id,),
        )
        version_number = db.execute(
            "SELECT COALESCE(MAX(version_number), 0) + 1 AS next_number "
            "FROM article_versions WHERE article_id = ?",
            (article_id,),
        ).fetchone()["next_number"]
        db.execute(
            """INSERT INTO article_versions
            (article_id, version_number, content, version_type, is_current)
            VALUES (?, ?, ?, 'manual', 1)""",
            (article_id, version_number, content),
        )
        db.execute(
            "UPDATE articles SET updated_at = ? WHERE id = ?", (now(), article_id)
        )
        db.commit()
        flash("Modifications enregistrées.", "success")
    return redirect(url_for("main.article_detail", article_id=article_id))


@main.post("/articles/<int:article_id>/validate")
def validate(article_id):
    db = get_db()
    current = db.execute(
        "SELECT content FROM article_versions WHERE article_id = ? AND is_current = 1",
        (article_id,),
    ).fetchone()
    if current is None:
        flash("Générez ou rédigez un article avant de le valider.", "error")
        return redirect(url_for("main.article_detail", article_id=article_id))
    db.execute("UPDATE article_versions SET is_current = 0 WHERE article_id = ?", (article_id,))
    version_number = db.execute(
        "SELECT COALESCE(MAX(version_number), 0) + 1 AS next_number "
        "FROM article_versions WHERE article_id = ?",
        (article_id,),
    ).fetchone()["next_number"]
    db.execute(
        """INSERT INTO article_versions
        (article_id, version_number, content, version_type, is_current)
        VALUES (?, ?, ?, 'validated', 1)""",
        (article_id, version_number, current["content"]),
    )
    db.execute(
        "UPDATE articles SET status = 'validated', updated_at = ? WHERE id = ?",
        (now(), article_id),
    )
    db.commit()
    flash("Article validé. Vous pouvez générer son audio.", "success")
    return redirect(url_for("main.article_detail", article_id=article_id))


@main.post("/articles/<int:article_id>/audio")
def audio(article_id):
    db = get_db()
    article = db.execute(
        """SELECT articles.*, categories.name AS category
        FROM articles JOIN categories ON categories.id = articles.category_id
        WHERE articles.id = ?""",
        (article_id,),
    ).fetchone()
    if article is None:
        return "Article introuvable", 404
    audio_id = None
    try:
        version = db.execute(
            "SELECT content FROM article_versions WHERE article_id = ? "
            "AND version_type = 'validated' AND is_current = 1",
            (article_id,),
        ).fetchone()
        if version is None:
            flash("Validez une version de l'article avant de générer l'audio.", "error")
            return redirect(url_for("main.article_detail", article_id=article_id))
        audio_id = db.execute(
            """INSERT INTO audios
            (article_id, file_path, language, provider, status)
            VALUES (?, '', ?, 'gtts', 'processing')""",
            (article_id, article["language"]),
        ).lastrowid
        filename = generate_audio(version["content"], article["language"], article_id)
        db.execute(
            "UPDATE audios SET file_path = ?, status = 'ready' WHERE id = ?",
            (filename, audio_id),
        )
    except Exception:
        logger.exception("Audio generation failed for article_id=%s", article_id)
        if audio_id is not None:
            db.execute(
                "UPDATE audios SET status = 'failed', error_message = ? WHERE id = ?",
                ("Échec de la génération audio.", audio_id),
            )
            db.commit()
        flash("La génération audio a échoué. Veuillez réessayer.", "error")
    else:
        db.execute(
            "UPDATE articles SET status = 'audio', updated_at = ? WHERE id = ?",
            (now(), article_id),
        )
        db.commit()
        flash("Audio généré avec succès.", "success")
    return redirect(url_for("main.article_detail", article_id=article_id))


@main.get("/audio/<path:filename>")
def audio_file(filename):
    return send_from_directory(Path(current_app.instance_path) / "audio", filename)
