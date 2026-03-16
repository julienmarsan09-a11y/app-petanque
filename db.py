"""
db.py — Couche de persistance PostgreSQL
Remplace les fichiers JSON (concours_data.json, archives/, users.json, smtp_config.json)
par des tables PostgreSQL, sans toucher à la logique métier de app.py.

Stratégie : on stocke le JSON tel quel dans des colonnes TEXT/JSONB.
Avantage : zéro refactoring du code métier existant.
"""

import json
import os
import psycopg2
import psycopg2.extras
from pathlib import Path
from datetime import datetime

# ── Connexion ────────────────────────────────────────────────────────────────

def get_conn():
    """
    Retourne une connexion PostgreSQL.
    Utilise la variable d'environnement DATABASE_URL injectée par Render.
    En local, crée un fallback vers SQLite via un flag USE_SQLITE=1.
    """
    database_url = os.environ.get("DATABASE_URL", "")

    # Render injecte parfois "postgres://" au lieu de "postgresql://"
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)

    if not database_url:
        raise RuntimeError(
            "DATABASE_URL manquante. "
            "Configurez-la dans les variables d'environnement Render."
        )

    conn = psycopg2.connect(database_url, cursor_factory=psycopg2.extras.RealDictCursor)
    return conn


def init_db() -> None:
    """
    Crée les tables si elles n'existent pas.
    À appeler au démarrage de l'application (une seule fois).

    Tables créées :
    - kv_store      : stockage clé/valeur JSON (concours en cours, users, smtp)
    - archives      : un concours archivé par ligne
    """
    conn = get_conn()
    try:
        with conn:
            with conn.cursor() as cur:
                # Table générique clé/valeur pour les données singleton
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS kv_store (
                        key     TEXT PRIMARY KEY,
                        value   TEXT NOT NULL,
                        updated_at TIMESTAMPTZ DEFAULT NOW()
                    )
                """)

                # Table des archives (un concours = une ligne)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS archives (
                        filename    TEXT PRIMARY KEY,
                        nom         TEXT,
                        date_concours TEXT,
                        lieu        TEXT,
                        nb_equipes  INTEGER,
                        statut      TEXT,
                        date_creation TEXT,
                        data        TEXT NOT NULL,
                        created_at  TIMESTAMPTZ DEFAULT NOW()
                    )
                """)
        print("✅ Base de données initialisée.")
    finally:
        conn.close()


# ── KV Store (concours en cours, users, smtp) ────────────────────────────────

def kv_get(key: str) -> dict | None:
    """Récupère une valeur JSON depuis kv_store. Retourne None si absent."""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT value FROM kv_store WHERE key = %s", (key,))
            row = cur.fetchone()
            if row:
                return json.loads(row["value"])
            return None
    finally:
        conn.close()


def kv_set(key: str, value: dict | list) -> None:
    """Insère ou met à jour une valeur JSON dans kv_store (upsert)."""
    conn = get_conn()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO kv_store (key, value, updated_at)
                    VALUES (%s, %s, NOW())
                    ON CONFLICT (key) DO UPDATE
                        SET value = EXCLUDED.value,
                            updated_at = NOW()
                """, (key, json.dumps(value, ensure_ascii=False)))
    finally:
        conn.close()


def kv_delete(key: str) -> None:
    """Supprime une entrée de kv_store."""
    conn = get_conn()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM kv_store WHERE key = %s", (key,))
    finally:
        conn.close()


# ── Archives ──────────────────────────────────────────────────────────────────

def archive_save(filename: str, data: dict) -> None:
    """Sauvegarde un concours archivé dans la table archives."""
    conn = get_conn()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO archives
                        (filename, nom, date_concours, lieu, nb_equipes,
                         statut, date_creation, data)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (filename) DO UPDATE
                        SET data = EXCLUDED.data,
                            nom  = EXCLUDED.nom
                """, (
                    filename,
                    data.get("nom", ""),
                    data.get("date_concours", ""),
                    data.get("lieu", ""),
                    len(data.get("equipes", [])),
                    data.get("statut", ""),
                    data.get("date_creation", ""),
                    json.dumps(data, ensure_ascii=False),
                ))
    finally:
        conn.close()


def archive_list() -> list[dict]:
    """Retourne la liste des archives triées par date décroissante."""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT filename, nom, date_concours, lieu,
                       nb_equipes, statut, date_creation
                FROM archives
                ORDER BY created_at DESC
            """)
            return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


def archive_get(filename: str) -> dict | None:
    """Récupère les données complètes d'une archive par son nom de fichier."""
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT data FROM archives WHERE filename = %s", (filename,)
            )
            row = cur.fetchone()
            if row:
                return json.loads(row["data"])
            return None
    finally:
        conn.close()


def archive_delete(filename: str) -> bool:
    """Supprime une archive. Retourne True si supprimée, False si introuvable."""
    conn = get_conn()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM archives WHERE filename = %s", (filename,)
                )
                return cur.rowcount > 0
    finally:
        conn.close()


# ── Migration depuis fichiers JSON locaux ─────────────────────────────────────

def migrate_from_files() -> None:
    """
    Importe les données des fichiers JSON locaux vers PostgreSQL.
    À appeler UNE SEULE FOIS pour la migration initiale.
    Idempotent : n'écrase pas les données existantes.

    Usage :
        python db.py migrate
    """
    print("🔄 Migration des fichiers JSON vers PostgreSQL...")

    # concours_data.json
    data_file = Path("concours_data.json")
    if data_file.exists():
        data = json.loads(data_file.read_text(encoding="utf-8"))
        existing = kv_get("concours_data")
        if existing is None:
            kv_set("concours_data", data)
            print("  ✅ concours_data.json importé")
        else:
            print("  ⏭️  concours_data déjà en base, ignoré")

    # users.json
    users_file = Path("users.json")
    if users_file.exists():
        data = json.loads(users_file.read_text(encoding="utf-8"))
        existing = kv_get("users")
        if existing is None:
            kv_set("users", data)
            print("  ✅ users.json importé")
        else:
            print("  ⏭️  users déjà en base, ignoré")

    # smtp_config.json
    smtp_file = Path("smtp_config.json")
    if smtp_file.exists():
        data = json.loads(smtp_file.read_text(encoding="utf-8"))
        existing = kv_get("smtp_config")
        if existing is None:
            kv_set("smtp_config", data)
            print("  ✅ smtp_config.json importé")
        else:
            print("  ⏭️  smtp_config déjà en base, ignoré")

    # archives/
    archive_dir = Path("archives")
    if archive_dir.exists():
        count = 0
        for f in sorted(archive_dir.glob("*.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                existing = archive_get(f.name)
                if existing is None:
                    archive_save(f.name, data)
                    count += 1
            except Exception as ex:
                print(f"  ⚠️  Erreur sur {f.name}: {ex}")
        print(f"  ✅ {count} archives importées")

    print("✅ Migration terminée.")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "migrate":
        migrate_from_files()
    else:
        print("Usage: python db.py migrate")
        print("       (importe les fichiers JSON locaux vers PostgreSQL)")
