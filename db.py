"""
db.py — Couche de persistance PostgreSQL [FIXED]
Utilise pg8000 (pure Python) compatible avec Python 3.14+
AVEC gestion d'erreurs robuste et retry logic
"""

import json
import os
import pg8000.native
from datetime import datetime
from urllib.parse import urlparse
import time


def get_conn(retries=3, delay=1):
    """Connexion PostgreSQL via DATABASE_URL avec retry."""
    url = os.environ.get("DATABASE_URL", "")
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    if not url:
        raise RuntimeError("DATABASE_URL manquante.")
    
    p = urlparse(url)
    last_error = None
    
    for attempt in range(retries):
        try:
            print(f"🔌 Tentative connexion BD ({attempt+1}/{retries})...")
            conn = pg8000.native.Connection(
                host=p.hostname,
                port=p.port or 5432,
                database=p.path.lstrip("/"),
                user=p.username,
                password=p.password,
                ssl_context=True,
            )
            print(f"✅ Connexion BD réussie")
            return conn
        except Exception as e:
            last_error = e
            print(f"⚠️ Erreur connexion (tentative {attempt+1}): {e}")
            if attempt < retries - 1:
                time.sleep(delay)
    
    raise RuntimeError(f"Impossible de se connecter à la BD après {retries} tentatives: {last_error}")


def init_db() -> None:
    """Crée les tables si elles n'existent pas."""
    conn = None
    try:
        conn = get_conn(retries=5, delay=2)
        print("📋 Création des tables...")
        
        conn.run("""
            CREATE TABLE IF NOT EXISTS kv_store (
                key        TEXT PRIMARY KEY,
                value      TEXT NOT NULL,
                updated_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        print("✅ Table kv_store créée")
        
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
        print("✅ Table archives créée")
        print("✅ Base de données initialisée.")
    except Exception as e:
        print(f"❌ Erreur init_db: {e}")
        raise
    finally:
        if conn:
            try:
                conn.close()
            except Exception as e:
                print(f"⚠️ Erreur fermeture connexion: {e}")


def kv_get(key: str):
    """Récupère une valeur (avec gestion d'erreur)."""
    conn = None
    try:
        conn = get_conn()
        rows = conn.run("SELECT value FROM kv_store WHERE key = :key", key=key)
        if rows:
            value = json.loads(rows[0][0])
            print(f"✓ kv_get('{key}') OK")
            return value
        print(f"ℹ️ kv_get('{key}') - clé non trouvée")
        return None
    except Exception as e:
        print(f"❌ Erreur kv_get('{key}'): {type(e).__name__}: {e}")
        return None
    finally:
        if conn:
            try:
                conn.close()
            except Exception as e:
                print(f"⚠️ Erreur fermeture: {e}")


def kv_set(key: str, value) -> None:
    """Sauvegarde une valeur (avec gestion d'erreur)."""
    conn = None
    try:
        conn = get_conn()
        json_str = json.dumps(value, ensure_ascii=False)
        conn.run("""
            INSERT INTO kv_store (key, value, updated_at)
            VALUES (:key, :value, NOW())
            ON CONFLICT (key) DO UPDATE
                SET value = EXCLUDED.value,
                    updated_at = NOW()
        """, key=key, value=json_str)
        print(f"✓ kv_set('{key}') OK ({len(json_str)} bytes)")
    except Exception as e:
        print(f"❌ Erreur kv_set('{key}'): {type(e).__name__}: {e}")
        raise
    finally:
        if conn:
            try:
                conn.close()
            except Exception as e:
                print(f"⚠️ Erreur fermeture: {e}")


def kv_delete(key: str) -> None:
    """Supprime une valeur (avec gestion d'erreur)."""
    conn = None
    try:
        conn = get_conn()
        conn.run("DELETE FROM kv_store WHERE key = :key", key=key)
        print(f"✓ kv_delete('{key}') OK")
    except Exception as e:
        print(f"❌ Erreur kv_delete('{key}'): {type(e).__name__}: {e}")
        raise
    finally:
        if conn:
            try:
                conn.close()
            except Exception as e:
                print(f"⚠️ Erreur fermeture: {e}")


def archive_save(filename: str, data: dict) -> None:
    """Sauvegarde une archive (avec gestion d'erreur)."""
    conn = None
    try:
        conn = get_conn()
        json_str = json.dumps(data, ensure_ascii=False)
        
        conn.run("""
            INSERT INTO archives
                (filename, nom, date_concours, lieu, nb_equipes,
                 statut, date_creation, data)
            VALUES (:filename, :nom, :date_concours, :lieu, :nb_equipes,
                    :statut, :date_creation, :data)
            ON CONFLICT (filename) DO UPDATE
                SET data = EXCLUDED.data,
                    nom  = EXCLUDED.nom,
                    created_at = NOW()
        """,
            filename=filename,
            nom=data.get("nom", ""),
            date_concours=data.get("date_concours", ""),
            lieu=data.get("lieu", ""),
            nb_equipes=len(data.get("equipes", [])),
            statut=data.get("statut", ""),
            date_creation=data.get("date_creation", ""),
            data=json_str,
        )
        print(f"✓ archive_save('{filename}') OK")
    except Exception as e:
        print(f"❌ Erreur archive_save('{filename}'): {type(e).__name__}: {e}")
        raise
    finally:
        if conn:
            try:
                conn.close()
            except Exception as e:
                print(f"⚠️ Erreur fermeture: {e}")


def archive_list() -> list:
    """Liste les archives (avec gestion d'erreur et fallback)."""
    conn = None
    try:
        conn = get_conn()
        rows = conn.run("""
            SELECT filename, nom, date_concours, lieu,
                   nb_equipes, statut, date_creation
            FROM archives
            ORDER BY created_at DESC
        """)
        
        keys = ["filename", "nom", "date_concours", "lieu",
                "nb_equipes", "statut", "date_creation"]
        result = []
        for row in rows:
            d = dict(zip(keys, row))
            d["fichier"] = d["filename"]  # alias pour compatibilité template
            result.append(d)
        
        print(f"✓ archive_list() OK - {len(result)} archives trouvées")
        return result
    except Exception as e:
        print(f"❌ Erreur archive_list(): {type(e).__name__}: {e}")
        return []  # Fallback : retourne liste vide au lieu de crash
    finally:
        if conn:
            try:
                conn.close()
            except Exception as e:
                print(f"⚠️ Erreur fermeture: {e}")


def archive_get(filename: str):
    """Récupère une archive (avec gestion d'erreur)."""
    conn = None
    try:
        conn = get_conn()
        rows = conn.run(
            "SELECT data FROM archives WHERE filename = :filename",
            filename=filename
        )
        if rows:
            data = json.loads(rows[0][0])
            print(f"✓ archive_get('{filename}') OK")
            return data
        print(f"ℹ️ archive_get('{filename}') - archive non trouvée")
        return None
    except Exception as e:
        print(f"❌ Erreur archive_get('{filename}'): {type(e).__name__}: {e}")
        return None
    finally:
        if conn:
            try:
                conn.close()
            except Exception as e:
                print(f"⚠️ Erreur fermeture: {e}")


def archive_delete(filename: str) -> bool:
    """Supprime une archive (avec gestion d'erreur)."""
    conn = None
    try:
        conn = get_conn()
        conn.run(
            "DELETE FROM archives WHERE filename = :filename",
            filename=filename
        )
        print(f"✓ archive_delete('{filename}') OK")
        return True
    except Exception as e:
        print(f"❌ Erreur archive_delete('{filename}'): {type(e).__name__}: {e}")
        return False
    finally:
        if conn:
            try:
                conn.close()
            except Exception as e:
                print(f"⚠️ Erreur fermeture: {e}")
