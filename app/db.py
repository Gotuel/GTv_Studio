import shutil
import sqlite3
from pathlib import Path

import click
from flask import current_app, g


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    slug TEXT NOT NULL UNIQUE,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS articles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    raw_content TEXT NOT NULL,
    level TEXT NOT NULL DEFAULT 'intermediate',
    language TEXT NOT NULL DEFAULT 'fr',
    category_id INTEGER NOT NULL,
    source TEXT,
    status TEXT NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'generating', 'review', 'validated', 'audio')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (category_id) REFERENCES categories (id)
);

CREATE TABLE IF NOT EXISTS article_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    article_id INTEGER NOT NULL,
    version_number INTEGER NOT NULL,
    content TEXT NOT NULL,
    version_type TEXT NOT NULL
        CHECK (version_type IN ('ai_generated', 'manual', 'validated')),
    is_current INTEGER NOT NULL DEFAULT 1 CHECK (is_current IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (article_id) REFERENCES articles (id) ON DELETE CASCADE,
    UNIQUE (article_id, version_number)
);

CREATE TABLE IF NOT EXISTS audios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    article_id INTEGER NOT NULL,
    file_path TEXT NOT NULL,
    language TEXT NOT NULL DEFAULT 'fr',
    provider TEXT NOT NULL DEFAULT 'gtts',
    status TEXT NOT NULL DEFAULT 'processing'
        CHECK (status IN ('processing', 'ready', 'failed')),
    error_message TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (article_id) REFERENCES articles (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_articles_category ON articles (category_id);
CREATE INDEX IF NOT EXISTS idx_articles_status ON articles (status);
CREATE INDEX IF NOT EXISTS idx_articles_created ON articles (created_at);
CREATE INDEX IF NOT EXISTS idx_versions_article ON article_versions (article_id);
CREATE INDEX IF NOT EXISTS idx_audios_article ON audios (article_id);
"""

DEFAULT_CATEGORIES = ("Actualités", "Politique", "Culture", "Sport", "Société")
POSTGRES_SCHEMA = """
CREATE TABLE IF NOT EXISTS categories (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    slug TEXT NOT NULL UNIQUE,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS articles (
    id BIGSERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    raw_content TEXT NOT NULL,
    level TEXT NOT NULL DEFAULT 'intermediate',
    language TEXT NOT NULL DEFAULT 'fr',
    category_id BIGINT NOT NULL REFERENCES categories(id),
    source TEXT,
    status TEXT NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'generating', 'review', 'validated', 'audio')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS article_versions (
    id BIGSERIAL PRIMARY KEY,
    article_id BIGINT NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
    version_number INTEGER NOT NULL,
    content TEXT NOT NULL,
    version_type TEXT NOT NULL
        CHECK (version_type IN ('ai_generated', 'manual', 'validated')),
    is_current INTEGER NOT NULL DEFAULT 1 CHECK (is_current IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (article_id, version_number)
);
CREATE TABLE IF NOT EXISTS audios (
    id BIGSERIAL PRIMARY KEY,
    article_id BIGINT NOT NULL REFERENCES articles(id) ON DELETE CASCADE,
    file_path TEXT NOT NULL,
    language TEXT NOT NULL DEFAULT 'fr',
    provider TEXT NOT NULL DEFAULT 'gtts',
    status TEXT NOT NULL DEFAULT 'processing'
        CHECK (status IN ('processing', 'ready', 'failed')),
    error_message TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_articles_category ON articles (category_id);
CREATE INDEX IF NOT EXISTS idx_articles_status ON articles (status);
CREATE INDEX IF NOT EXISTS idx_articles_created ON articles (created_at);
CREATE INDEX IF NOT EXISTS idx_versions_article ON article_versions (article_id);
CREATE INDEX IF NOT EXISTS idx_audios_article ON audios (article_id);
"""


class PostgresConnection:
    def __init__(self, connection):
        self.connection = connection

    def execute(self, sql, parameters=()):
        cursor = self.connection.cursor()
        cursor.execute(sql.replace("?", "%s"), parameters)
        return cursor

    def executescript(self, sql):
        with self.connection.cursor() as cursor:
            cursor.execute(sql)

    def commit(self):
        self.connection.commit()

    def close(self):
        self.connection.close()


LEGACY_SUPPORT_SCHEMA = """
CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    slug TEXT NOT NULL UNIQUE,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS article_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    article_id INTEGER NOT NULL,
    version_number INTEGER NOT NULL,
    content TEXT NOT NULL,
    version_type TEXT NOT NULL,
    is_current INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS audios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    article_id INTEGER NOT NULL,
    file_path TEXT NOT NULL,
    language TEXT NOT NULL DEFAULT 'fr',
    provider TEXT NOT NULL DEFAULT 'gtts',
    status TEXT NOT NULL DEFAULT 'ready',
    error_message TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


def get_db():
    if "db" not in g:
        database_url = current_app.config.get("DATABASE_URL")
        if database_url:
            import psycopg
            from psycopg.rows import dict_row

            connection = psycopg.connect(
                database_url,
                connect_timeout=10,
                row_factory=dict_row,
                application_name="gtv-studio",
            )
            g.db = PostgresConnection(connection)
        else:
            Path(current_app.config["DATABASE_PATH"]).parent.mkdir(
                parents=True, exist_ok=True
            )
            g.db = sqlite3.connect(current_app.config["DATABASE_PATH"], timeout=15)
            g.db.row_factory = sqlite3.Row
            g.db.execute("PRAGMA foreign_keys = ON")
            g.db.execute("PRAGMA busy_timeout = 15000")
    return g.db


def close_db(_error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def _slug(value):
    import re
    import unicodedata

    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", ascii_value).strip("-")


def _seed_categories(db):
    for name in DEFAULT_CATEGORIES:
        db.execute(
            "INSERT INTO categories (name, slug) VALUES (?, ?) "
            "ON CONFLICT (name) DO NOTHING",
            (name, _slug(name)),
        )


def _category_id(db, name):
    name = (name or "Actualités").strip() or "Actualités"
    row = db.execute("SELECT id FROM categories WHERE name = ?", (name,)).fetchone()
    if row:
        return row["id"]
    row = db.execute(
        "INSERT INTO categories (name, slug) VALUES (?, ?) RETURNING id",
        (name, _slug(name)),
    ).fetchone()
    return row["id"]


def _is_legacy_articles(db):
    columns = {
        row["name"] for row in db.execute("PRAGMA table_info(articles)").fetchall()
    }
    return bool(columns & {"generated_content", "final_content", "category", "audio_path"})


def _migrate_legacy_articles(db):
    db.execute("PRAGMA foreign_keys = OFF")
    db.execute("ALTER TABLE articles RENAME TO articles_legacy")
    db.executescript(
        """
        CREATE TABLE articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            raw_content TEXT NOT NULL,
            level TEXT NOT NULL DEFAULT 'intermediate',
            language TEXT NOT NULL DEFAULT 'fr',
            category_id INTEGER NOT NULL,
            source TEXT,
            status TEXT NOT NULL DEFAULT 'draft'
                CHECK (status IN ('draft', 'generating', 'review', 'validated', 'audio')),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (category_id) REFERENCES categories (id)
        );
        """
    )
    legacy_rows = db.execute("SELECT * FROM articles_legacy").fetchall()
    for row in legacy_rows:
        category_id = _category_id(db, row["category"])
        db.execute(
            """INSERT INTO articles
            (id, title, raw_content, level, language, category_id, source,
             status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                row["id"], row["title"], row["raw_content"], row["level"],
                row["language"], category_id, row["source"], row["status"],
                row["created_at"], row["updated_at"],
            ),
        )
        if row["generated_content"]:
            db.execute(
                """INSERT INTO article_versions
                (article_id, version_number, content, version_type, is_current)
                VALUES (?, 1, ?, 'ai_generated', ?)""",
                (row["id"], row["generated_content"], int(not row["final_content"])),
            )
        if row["final_content"]:
            version_number = 2 if row["generated_content"] else 1
            version_type = "validated" if row["status"] in ("validated", "audio") else "manual"
            db.execute(
                """INSERT INTO article_versions
                (article_id, version_number, content, version_type, is_current)
                VALUES (?, ?, ?, ?, 1)""",
                (row["id"], version_number, row["final_content"], version_type),
            )
        if row["audio_path"]:
            db.execute(
                """INSERT INTO audios
                (article_id, file_path, language, provider, status)
                VALUES (?, ?, ?, 'gtts', 'ready')""",
                (row["id"], row["audio_path"], row["language"]),
            )
    db.execute("DROP TABLE articles_legacy")
    db.execute("PRAGMA foreign_keys = ON")


def _rebuild_child_table_constraints(db):
    for table, columns in (
        (
            "article_versions",
            "id, article_id, version_number, content, version_type, is_current, created_at",
        ),
        (
            "audios",
            "id, article_id, file_path, language, provider, status, error_message, created_at",
        ),
    ):
        definition = db.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table,),
        ).fetchone()
        if not definition or "articles_legacy" not in definition["sql"]:
            continue
        db.execute(f"ALTER TABLE {table} RENAME TO {table}_legacy")
        if table == "article_versions":
            db.executescript(
                """CREATE TABLE article_versions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    article_id INTEGER NOT NULL,
                    version_number INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    version_type TEXT NOT NULL
                        CHECK (version_type IN ('ai_generated', 'manual', 'validated')),
                    is_current INTEGER NOT NULL DEFAULT 1 CHECK (is_current IN (0, 1)),
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (article_id) REFERENCES articles (id) ON DELETE CASCADE,
                    UNIQUE (article_id, version_number)
                );"""
            )
        else:
            db.executescript(
                """CREATE TABLE audios (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    article_id INTEGER NOT NULL,
                    file_path TEXT NOT NULL,
                    language TEXT NOT NULL DEFAULT 'fr',
                    provider TEXT NOT NULL DEFAULT 'gtts',
                    status TEXT NOT NULL DEFAULT 'processing'
                        CHECK (status IN ('processing', 'ready', 'failed')),
                    error_message TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (article_id) REFERENCES articles (id) ON DELETE CASCADE
                );"""
            )
        db.execute(
            f"INSERT INTO {table} ({columns}) SELECT {columns} FROM {table}_legacy"
        )
        db.execute(f"DROP TABLE {table}_legacy")


def _restore_missing_legacy_data(db, database_path):
    backup = database_path.with_name(f"{database_path.stem}.backup.sqlite3")
    if not backup.exists():
        return
    if db.execute("SELECT COUNT(*) AS total FROM article_versions").fetchone()["total"]:
        return
    legacy = sqlite3.connect(backup)
    legacy.row_factory = sqlite3.Row
    try:
        rows = legacy.execute("SELECT * FROM articles").fetchall()
    except sqlite3.Error:
        legacy.close()
        return
    for row in rows:
        exists = db.execute(
            "SELECT 1 FROM articles WHERE id = ?", (row["id"],)
        ).fetchone()
        if not exists:
            continue
        version_number = 0
        if row["generated_content"]:
            version_number += 1
            db.execute(
                """INSERT INTO article_versions
                (article_id, version_number, content, version_type, is_current)
                VALUES (?, ?, ?, 'ai_generated', ?)""",
                (row["id"], version_number, row["generated_content"], int(not row["final_content"])),
            )
        if row["final_content"]:
            version_number += 1
            db.execute(
                """INSERT INTO article_versions
                (article_id, version_number, content, version_type, is_current)
                VALUES (?, ?, ?, ?, 1)""",
                (
                    row["id"], version_number, row["final_content"],
                    "validated" if row["status"] in ("validated", "audio") else "manual",
                ),
            )
        if row["audio_path"]:
            db.execute(
                """INSERT INTO audios
                (article_id, file_path, language, provider, status)
                VALUES (?, ?, ?, 'gtts', 'ready')""",
                (row["id"], row["audio_path"], row["language"]),
            )
    legacy.close()


def init_db():
    db = get_db()
    if current_app.config.get("DATABASE_URL"):
        db.executescript(POSTGRES_SCHEMA)
        _seed_categories(db)
        db.commit()
        return
    database_path = Path(current_app.config["DATABASE_PATH"])
    has_articles = db.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'articles'"
    ).fetchone()
    if has_articles and _is_legacy_articles(db):
        backup = database_path.with_name(f"{database_path.stem}.backup.sqlite3")
        if not backup.exists() and database_path.exists():
            shutil.copy2(database_path, backup)
    if has_articles and _is_legacy_articles(db):
        db.executescript(LEGACY_SUPPORT_SCHEMA)
        _seed_categories(db)
        _migrate_legacy_articles(db)
        db.executescript(
            """
            CREATE INDEX IF NOT EXISTS idx_articles_category ON articles (category_id);
            CREATE INDEX IF NOT EXISTS idx_articles_status ON articles (status);
            CREATE INDEX IF NOT EXISTS idx_articles_created ON articles (created_at);
            CREATE INDEX IF NOT EXISTS idx_versions_article ON article_versions (article_id);
            CREATE INDEX IF NOT EXISTS idx_audios_article ON audios (article_id);
            """
        )
    else:
        db.executescript(SCHEMA)
        _seed_categories(db)
    _rebuild_child_table_constraints(db)
    _restore_missing_legacy_data(db, database_path)
    db.commit()


def init_app(app):
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)
    app.cli.add_command(inspect_db_command)
    app.cli.add_command(migrate_local_db_command)


@click.command("init-db")
def init_db_command():
    init_db()
    click.echo("Base SQLite initialisée.")


@click.command("inspect-db")
def inspect_db_command():
    db = get_db()
    if current_app.config.get("DATABASE_URL"):
        tables = db.execute(
            """SELECT table_name AS name FROM information_schema.tables
            WHERE table_schema = 'public' ORDER BY table_name"""
        ).fetchall()
    else:
        tables = db.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
        ).fetchall()
    for table in tables:
        if table["name"] == "sqlite_sequence":
            continue
        count = db.execute(
            f'SELECT COUNT(*) AS total FROM "{table["name"]}"'
        ).fetchone()["total"]
        click.echo(f'{table["name"]}: {count} enregistrement(s)')


@click.command("migrate-local-db")
@click.option(
    "--source",
    default="instance/2gc_converter.sqlite3",
    show_default=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
)
def migrate_local_db_command(source):
    if not current_app.config.get("DATABASE_URL"):
        raise click.ClickException("DATABASE_URL doit pointer vers PostgreSQL.")
    if current_app.config["STORAGE_BACKEND"] != "supabase":
        raise click.ClickException("STORAGE_BACKEND doit être « supabase ».")

    local = sqlite3.connect(source)
    local.row_factory = sqlite3.Row
    remote = get_db()
    from .storage import upload_audio

    try:
        for category in local.execute("SELECT * FROM categories"):
            remote.execute(
                """INSERT INTO categories (id, name, slug, is_active, created_at)
                VALUES (?, ?, ?, ?, ?) ON CONFLICT (id) DO NOTHING""",
                tuple(category[key] for key in (
                    "id", "name", "slug", "is_active", "created_at"
                )),
            )

        for article in local.execute("SELECT * FROM articles"):
            remote.execute(
                """INSERT INTO articles
                (id, title, raw_content, level, language, category_id, source,
                 status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (id) DO NOTHING""",
                tuple(article[key] for key in (
                    "id", "title", "raw_content", "level", "language",
                    "category_id", "source", "status", "created_at", "updated_at"
                )),
            )

        for version in local.execute("SELECT * FROM article_versions"):
            remote.execute(
                """INSERT INTO article_versions
                (id, article_id, version_number, content, version_type, is_current, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (id) DO NOTHING""",
                tuple(version[key] for key in (
                    "id", "article_id", "version_number", "content",
                    "version_type", "is_current", "created_at"
                )),
            )

        audio_directory = Path(current_app.config["AUDIO_STORAGE_PATH"])
        for audio in local.execute("SELECT * FROM audios"):
            audio_path = audio_directory / Path(audio["file_path"]).name
            if audio["status"] == "ready":
                if not audio_path.is_file():
                    raise click.ClickException(
                        f"Fichier audio local introuvable : {audio_path}"
                    )
                upload_audio(
                    audio["file_path"],
                    audio_path.read_bytes(),
                    overwrite=True,
                )
            remote.execute(
                """INSERT INTO audios
                (id, article_id, file_path, language, provider, status, error_message, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (id) DO NOTHING""",
                tuple(audio[key] for key in (
                    "id", "article_id", "file_path", "language",
                    "provider", "status", "error_message", "created_at"
                )),
            )

        for table in ("categories", "articles", "article_versions", "audios"):
            remote.execute(
                f"""SELECT setval(
                    pg_get_serial_sequence('{table}', 'id'),
                    GREATEST(COALESCE((SELECT MAX(id) FROM {table}), 1), 1),
                    EXISTS(SELECT 1 FROM {table})
                )"""
            )
        remote.commit()
    except Exception:
        remote.connection.rollback()
        raise
    finally:
        local.close()
    click.echo(f"Migration terminée depuis {source}.")
