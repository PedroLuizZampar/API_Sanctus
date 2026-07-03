import time
import logging
import psycopg2
from psycopg2 import pool
from app.core import config

logger = logging.getLogger(__name__)

db_pool = None

def init_db_pool():
    """Inicializa o ThreadedConnectionPool."""
    global db_pool
    if not config.NEON_DATABASE_URL:
        raise RuntimeError("Variável NEON_DATABASE_URL não configurada.")
    
    try:
        logger.info("Inicializando ThreadedConnectionPool...")
        db_pool = psycopg2.pool.ThreadedConnectionPool(
            1, 10, config.NEON_DATABASE_URL,
            options="-c statement_timeout=30000"
        )
        logger.info("ThreadedConnectionPool inicializado com sucesso.")
    except Exception as e:
        logger.error(f"Erro ao inicializar o Connection Pool: {e}")
        raise

def close_db_pool():
    """Fecha todas as conexões do pool."""
    global db_pool
    if db_pool:
        logger.info("Fechando ThreadedConnectionPool...")
        db_pool.closeall()
        logger.info("ThreadedConnectionPool fechado.")

def get_db_connection():
    """
    FastAPI dependency generator.
    Entrega uma conexão do pool e garante commit/rollback e devolução.
    """
    global db_pool
    if db_pool is None:
        init_db_pool()
        
    conn = db_pool.getconn()
    conn.autocommit = False
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(f"Transação falhou, rollback executado: {e}")
        raise
    finally:
        db_pool.putconn(conn)

def garantir_tabelas(conn):
    """Cria as tabelas se não existirem."""
    with conn.cursor() as cur:
        # Garantir extensão pgcrypto para gen_random_uuid se necessário
        cur.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto";')
        
        cur.execute("""
            CREATE TABLE IF NOT EXISTS meditacoes_evangelho (
                id SERIAL PRIMARY KEY,
                conteudo TEXT NOT NULL,
                data DATE UNIQUE NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS curiosidades_catolicas (
                id SERIAL PRIMARY KEY,
                conteudo TEXT NOT NULL,
                data DATE UNIQUE NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS santos_do_dia (
                id SERIAL PRIMARY KEY,
                conteudo TEXT NOT NULL,
                data DATE UNIQUE NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS liturgias_diarias (
                id SERIAL PRIMARY KEY,
                conteudo TEXT NOT NULL,
                data DATE UNIQUE NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                nome TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS favorites (
                id TEXT PRIMARY KEY,
                user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                type TEXT NOT NULL,
                book_slug TEXT NOT NULL,
                book_title TEXT,
                chapter_id INTEGER,
                chapter_name TEXT,
                paragraph_number INTEGER NOT NULL,
                paragraph_text TEXT NOT NULL,
                timestamp BIGINT NOT NULL,
                group_id TEXT,
                group_range TEXT,
                updated_at BIGINT NOT NULL,
                is_deleted BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS highlights (
                id TEXT PRIMARY KEY,
                user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                type TEXT NOT NULL,
                book_slug TEXT NOT NULL,
                chapter_id INTEGER NOT NULL,
                paragraph_number INTEGER NOT NULL,
                start_word_index INTEGER NOT NULL,
                end_word_index INTEGER NOT NULL,
                highlighted_text TEXT NOT NULL,
                color TEXT NOT NULL,
                timestamp BIGINT NOT NULL,
                end_paragraph_number INTEGER,
                end_word_index_end INTEGER,
                updated_at BIGINT NOT NULL,
                is_deleted BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS chats (
                id TEXT PRIMARY KEY,
                user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                title TEXT NOT NULL,
                created_at BIGINT NOT NULL,
                updated_at BIGINT NOT NULL,
                messages_json TEXT NOT NULL,
                is_deleted BOOLEAN DEFAULT FALSE,
                created_at_db TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        cur.execute("""
            CREATE TABLE IF NOT EXISTS activities (
                id TEXT PRIMARY KEY,
                user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                titulo TEXT NOT NULL,
                dia TEXT,
                horario TEXT NOT NULL,
                lembrete_ativo BOOLEAN DEFAULT FALSE,
                lembrete_minutos_antes INTEGER DEFAULT 0,
                repetir BOOLEAN DEFAULT FALSE,
                frequencia TEXT,
                dias_semana TEXT,
                cor TEXT NOT NULL,
                mensagem_lembrete TEXT DEFAULT NULL,
                terminar_tipo TEXT DEFAULT 'nunca',
                terminar_vezes INTEGER DEFAULT 0,
                terminar_data TEXT DEFAULT NULL,
                updated_at BIGINT NOT NULL,
                is_deleted BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS activity_completions (
                id TEXT PRIMARY KEY,
                user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                activity_id TEXT REFERENCES activities(id) ON DELETE CASCADE,
                data TEXT NOT NULL,
                updated_at BIGINT NOT NULL,
                is_deleted BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        cur.execute("CREATE INDEX IF NOT EXISTS idx_favorites_user_sync ON favorites(user_id, updated_at);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_highlights_user_sync ON highlights(user_id, updated_at);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_chats_user_sync ON chats(user_id, updated_at);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_activities_user_sync ON activities(user_id, updated_at);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_activity_completions_user_sync ON activity_completions(user_id, updated_at);")
        
        cur.execute("""
            CREATE TABLE IF NOT EXISTS activity_exclusions (
                id TEXT PRIMARY KEY,
                user_id UUID REFERENCES users(id) ON DELETE CASCADE,
                activity_id TEXT REFERENCES activities(id) ON DELETE CASCADE,
                data TEXT NOT NULL,
                updated_at BIGINT NOT NULL,
                is_deleted BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_activity_exclusions_user_sync ON activity_exclusions(user_id, updated_at);")

        # Migrações seguras
        try:
            cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS reset_token TEXT DEFAULT NULL;")
            cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS reset_token_expires BIGINT DEFAULT NULL;")
            cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS avatar_url TEXT DEFAULT NULL;")
            cur.execute("ALTER TABLE activities DROP COLUMN IF EXISTS categoria;")
            cur.execute("ALTER TABLE activities ADD COLUMN IF NOT EXISTS terminar_tipo TEXT DEFAULT 'nunca';")
            cur.execute("ALTER TABLE activities ADD COLUMN IF NOT EXISTS terminar_vezes INTEGER DEFAULT 0;")
            cur.execute("ALTER TABLE activities ADD COLUMN IF NOT EXISTS terminar_data TEXT DEFAULT NULL;")
            cur.execute("ALTER TABLE activities ADD COLUMN IF NOT EXISTS icone TEXT DEFAULT NULL;")
        except Exception as me:
            logger.warning(f"Erro ao adicionar/remover colunas na inicialização: {me}")
    conn.commit()
    logger.info("Tabelas verificadas/criadas no banco de dados.")
