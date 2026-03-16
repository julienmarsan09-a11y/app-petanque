"""
db.py — Couche de persistance PostgreSQL
Utilise pg8000 (pure Python) compatible avec Python 3.14+
"""

import json
import os
import pg8000.native
from datetime import datetime
from urllib.parse import urlparse


def get_conn():
    """Connexion PostgreSQL via DATABASE_URL."""
    url = os.environ.get("DATABASE_URL", "")
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    if not url:
        raise RuntimeError("DATABASE_URL manquante.")
    p = urlparse(url)
    return pg8000.native.Connection(
        host=p.hostname,
        port=p.port or 5432,
        database=p.path.lstrip("/"),
        user=p.username,
        password=p.password,
        ssl_context=True,
    )


def init_db() -> None:
    """Crée les tables si elles n'existent pas."""
    conn = get_conn()
    try:
        conn.run("""
            CREATE TABLE IF NOT EXISTS kv_store (
                key        TEXT PRIMARY KEY,
                value      TEXT NOT NULL,
                updated_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        conn.run("""
            CREATE TABLE IF NOT EXISTS archives (
                filename      TEXT PRIMARY KEY,
                nom           TEXT,
                date_concours TEXT,
                lieu          TEXT,
                nb_equipes    INTEGER,
                statut        TEXT,
                date_creation TEXT,
                data          TEXT NOT NULL,
                created_at    TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        print("✅ Base de données initialisée.")
    finally:
        conn.close()


def kv_get(key: str):
    conn = get_conn()
    try:
        rows = conn.run("SELECT value FROM kv_store WHERE key = :key", key=key)
        if rows:
            return json.loads(rows[0][0])
        return None
    finally:
        conn.close()


def kv_set(key: str, value) -> None:
    conn = get_conn()
    try:
        conn.run("""
            INSERT INTO kv_store (key, value, updated_at)
            VALUES (:key, :value, NOW())
            ON CONFLICT (key) DO UPDATE
                SET value = EXCLUDED.value,
                    updated_at = NOW()
        """, key=key, value=json.dumps(value, ensure_ascii=False))
    finally:
        conn.close()


def kv_delete(key: str) -> None:
    conn = get_conn()
    try:
        conn.run("DELETE FROM kv_store WHERE key = :key", key=key)
    finally:
        conn.close()


def archive_save(filename: str, data: dict) -> None:
    conn = get_conn()
    try:
        conn.run("""
            INSERT INTO archives
                (filename, nom, date_concours, lieu, nb_equipes,
                 statut, date_creation, data)
            VALUES (:filename, :nom, :date_concours, :lieu, :nb_equipes,
                    :statut, :date_creation, :data)
            ON CONFLICT (filename) DO UPDATE
                SET data = EXCLUDED.data,
                    nom  = EXCLUDED.nom
        """,
            filename=filename,
            nom=data.get("nom", ""),
            date_concours=data.get("date_concours", ""),
            lieu=data.get("lieu", ""),
            nb_equipes=len(data.get("equipes", [])),
            statut=data.get("statut", ""),
            date_creation=data.get("date_creation", ""),
            data=json.dumps(data, ensure_ascii=False),
        )
    finally:
        conn.close()


def archive_list() -> list:
    conn = get_conn()
    try:
        rows = conn.run("""
            SELECT filename, nom, date_concours, lieu,
                   nb_equipes, statut, date_creation
            FROM archives
            ORDER BY created_at DESC
        """)
        keys = ["filename", "nom", "date_concours", "lieu",
                "nb_equipes", "statut", "date_creation"]
        return [dict(zip(keys, row)) for row in rows]
    finally:
        conn.close()


def archive_get(filename: str):
    conn = get_conn()
    try:
        rows = conn.run(
            "SELECT data FROM archives WHERE filename = :filename",
            filename=filename
        )
        if rows:
            return json.loads(rows[0][0])
        return None
    finally:
        conn.close()


def archive_delete(filename: str) -> bool:
    conn = get_conn()
    try:
        conn.run(
            "DELETE FROM archives WHERE filename = :filename",
            filename=filename
        )
        return True
    except Exception:
        return False
    finally:
        conn.close()
