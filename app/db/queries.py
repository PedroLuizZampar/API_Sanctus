import logging
from psycopg2 import sql

logger = logging.getLogger(__name__)

# =============================================================================
# Queries de Usuário (users)
# =============================================================================

def obter_usuario_por_email(conn, email: str):
    """Busca um usuário no banco pelo e-mail."""
    with conn.cursor() as cur:
        cur.execute("SELECT id, nome, email, password_hash, avatar_url FROM users WHERE email = %s", (email,))
        return cur.fetchone()

def obter_usuario_por_id(conn, user_id: str):
    """Busca um usuário no banco pelo ID (UUID)."""
    with conn.cursor() as cur:
        cur.execute("SELECT id, nome, email, password_hash, avatar_url FROM users WHERE id = %s", (user_id,))
        return cur.fetchone()

def criar_usuario(conn, nome: str, email: str, password_hash: str):
    """Cadastra um novo usuário."""
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO users (nome, email, password_hash) VALUES (%s, %s, %s) RETURNING id, nome, email, avatar_url",
            (nome, email, password_hash)
        )
        return cur.fetchone()

def atualizar_email_usuario(conn, user_id: str, new_email: str):
    """Atualiza o e-mail do usuário."""
    with conn.cursor() as cur:
        cur.execute("UPDATE users SET email = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s", (new_email, user_id))

def atualizar_senha_usuario(conn, user_id: str, new_password_hash: str):
    """Atualiza a senha do usuário."""
    with conn.cursor() as cur:
        cur.execute("UPDATE users SET password_hash = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s", (new_password_hash, user_id))

def atualizar_reset_token_usuario(conn, email: str, token: str, expires: int):
    """Atualiza o token de reset de senha e expiração."""
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE users SET reset_token = %s, reset_token_expires = %s, updated_at = CURRENT_TIMESTAMP WHERE email = %s",
            (token, expires, email)
        )

def obter_usuario_por_reset_token(conn, email: str, token: str):
    """Busca usuário pelo token de reset e verifica validade."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, reset_token_expires FROM users WHERE email = %s AND reset_token = %s",
            (email, token)
        )
        return cur.fetchone()

def atualizar_avatar_usuario(conn, user_id: str, avatar_url: str):
    """Atualiza a URL do avatar do usuário."""
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE users SET avatar_url = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s",
            (avatar_url, user_id)
        )

# =============================================================================
# Queries de Cache Diário (meditações, curiosidades, santos, liturgia)
# =============================================================================

def obter_meditacao_por_data(conn, data: str):
    """Busca meditação salva para uma data específica."""
    with conn.cursor() as cur:
        cur.execute("SELECT conteudo FROM meditacoes_evangelho WHERE data = %s", (data,))
        row = cur.fetchone()
        return row[0] if row else None

def salvar_meditacao(conn, data: str, conteudo: str):
    """Salva meditação gerada."""
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO meditacoes_evangelho (conteudo, data) VALUES (%s, %s) ON CONFLICT (data) DO UPDATE SET conteudo = EXCLUDED.conteudo",
            (conteudo, data)
        )

def obter_curiosidade_por_data(conn, data: str):
    """Busca curiosidade salva para uma data específica."""
    with conn.cursor() as cur:
        cur.execute("SELECT conteudo FROM curiosidades_catolicas WHERE data = %s", (data,))
        row = cur.fetchone()
        return row[0] if row else None

def salvar_curiosidade(conn, data: str, conteudo: str):
    """Salva curiosidade gerada."""
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO curiosidades_catolicas (conteudo, data) VALUES (%s, %s) ON CONFLICT (data) DO UPDATE SET conteudo = EXCLUDED.conteudo",
            (conteudo, data)
        )

def obter_santo_por_data(conn, data: str):
    """Busca santo do dia salvo para uma data específica."""
    with conn.cursor() as cur:
        cur.execute("SELECT conteudo FROM santos_do_dia WHERE data = %s", (data,))
        row = cur.fetchone()
        return row[0] if row else None

def salvar_santo(conn, data: str, conteudo: str):
    """Salva santo do dia."""
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO santos_do_dia (conteudo, data) VALUES (%s, %s) ON CONFLICT (data) DO UPDATE SET conteudo = EXCLUDED.conteudo",
            (conteudo, data)
        )

def obter_liturgia_por_data(conn, data: str):
    """Busca liturgia salva para uma data específica."""
    with conn.cursor() as cur:
        cur.execute("SELECT conteudo FROM liturgias_diarias WHERE data = %s", (data,))
        row = cur.fetchone()
        return row[0] if row else None

def salvar_liturgia(conn, data: str, conteudo: str):
    """Salva liturgia diária."""
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO liturgias_diarias (conteudo, data) VALUES (%s, %s) ON CONFLICT (data) DO UPDATE SET conteudo = EXCLUDED.conteudo",
            (conteudo, data)
        )
