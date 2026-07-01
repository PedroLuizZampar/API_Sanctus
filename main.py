import os
import random
import asyncio
import time
import logging
import re
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
import psycopg2
from psycopg2 import sql
import bcrypt
import jwt
from fastapi import FastAPI, HTTPException, Query, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from google import genai
from dotenv import load_dotenv

# =============================================================================
# Configuração de Logging
# =============================================================================
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Carrega variáveis locais de ambiente para execução em desenvolvimento.
load_dotenv()

# =============================================================================
# Variáveis de Ambiente
# =============================================================================
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
NEON_DATABASE_URL = os.environ.get("NEON_DATABASE_URL", "")
MAGISTERIUM_API_KEY = os.environ.get("MAGISTERIUM_API_KEY", "")
SANCTUS_APP_TOKEN = os.environ.get("SANCTUS_APP_TOKEN", "")

# =============================================================================
# Configuração de Segurança e JWT
# =============================================================================
JWT_SECRET = os.environ.get("JWT_SECRET", "super_secret_sanctus_key_2026_xyz")
JWT_ALGORITHM = "HS256"
TOKEN_EXPIRE_MINUTES = 60 * 24 * 30  # 30 dias

def hash_password(password: str) -> str:
    """Gera hash de senha usando bcrypt."""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifica se a senha coincide com o hash do banco."""
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except Exception:
        return False

def create_access_token(user_id: str, email: str) -> str:
    """Cria um token JWT de acesso para o usuário."""
    expire = datetime.utcnow() + timedelta(minutes=TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": str(user_id),
        "email": email,
        "exp": expire
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def get_current_user_id(authorization: str = Header(..., alias="Authorization")) -> str:
    """Valida o token JWT recebido no Header Authorization e retorna o user_id."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Formato de token inválido. Use Bearer <token>")
    token = authorization.split(" ")[1]
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Token inválido: sub ausente")
        return user_id
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expirado")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token inválido")


# =============================================================================
# Modelos de Dados Pydantic
# =============================================================================
from pydantic import BaseModel
from typing import List, Optional

class RegisterRequest(BaseModel):
    nome: str
    email: str
    password: str

class LoginRequest(BaseModel):
    email: str
    password: str

class FavoriteChangeItem(BaseModel):
    id: str
    type: str
    book_slug: str
    book_title: Optional[str] = None
    chapter_id: Optional[int] = None
    chapter_name: Optional[str] = None
    paragraph_number: int
    paragraph_text: str
    timestamp: int
    group_id: Optional[str] = None
    group_range: Optional[str] = None
    updated_at: int
    is_deleted: bool

class HighlightChangeItem(BaseModel):
    id: str
    type: str
    book_slug: str
    chapter_id: int
    paragraph_number: int
    start_word_index: int
    end_word_index: int
    highlighted_text: str
    color: str
    timestamp: int
    end_paragraph_number: Optional[int] = None
    end_word_index_end: Optional[int] = None
    updated_at: int
    is_deleted: bool

class ChatChangeItem(BaseModel):
    id: str
    title: str
    created_at: int
    updated_at: int
    messages_json: str
    is_deleted: bool

class SyncRequest(BaseModel):
    last_sync_timestamp: int
    favorites: List[FavoriteChangeItem]
    highlights: List[HighlightChangeItem]
    chats: Optional[List[ChatChangeItem]] = []

class UpdateEmailRequest(BaseModel):
    new_email: str

class UpdatePasswordRequest(BaseModel):
    current_password: str
    new_password: str

class ForgotPasswordRequest(BaseModel):
    email: str

class ResetPasswordRequest(BaseModel):
    email: str
    token: str
    new_password: str


# =============================================================================
# Cliente do Gemini (biblioteca oficial google-genai)
# =============================================================================
gemini_client = None
GEMINI_MODEL = "gemini-2.5-flash"


def get_gemini_client() -> genai.Client:
    """Inicializa o cliente Gemini apenas quando necessário."""
    global gemini_client
    if gemini_client is None:
        if not GEMINI_API_KEY:
            raise RuntimeError("Variável GEMINI_API_KEY não configurada.")
        gemini_client = genai.Client(api_key=GEMINI_API_KEY)
    return gemini_client

# =============================================================================
# Prompts
# =============================================================================
PROMPT_EVANGELHO = """
  Atue como um Diretor Espiritual e Teólogo Católico de profunda sensibilidade pastoral. Quero que você crie uma reflexão litúrgica diária baseada no Evangelho do dia. O texto deve ser estritamente devocional, com sólida teologia, mas escrito de forma natural, acolhedora e de fácil compreensão para o fiel leigo. 

Não insira o texto do Evangelho por extenso, concentre-se exclusivamente na meditação profunda sobre ele. Não responda como um modelo de IA; comece diretamente no conteúdo, sem saudações or introduções formais.

A estrutura geral de títulos (H2 e H3) e o uso de negritos devem seguir rigorosamente o modelo abaixo, mas a organização interna do conteúdo (seja por parágrafos fluídos, listas ou blocos de citação, apenas tabelas que não) fica totalmente a seu critério, utilizando o formato que você considerar mais didático e profundo para o tema do dia.

## Contextualização Litúrgica
Crie uma introdução situando o leitor na liturgia de hoje. Use a fórmula básica: "Como hoje é [Dia da Semana], [Data por extenso], a Igreja celebra a [Semana e Tempo Litúrgico]. A liturgia de hoje nos convida a...". Faça uma ponte direta entre o tempo litúrgico e o tema central do Evangelho, preparando a alma do leitor.

---

## A Mensagem do Dia: [Subtítulo Curto e Impactante]
Desenvolva a mensagem central do Evangelho. Você deve abordar o contexto teológico (o que Jesus quis ensinar originalmente naquele momento histórico, indo além da superfície) e a conexão com o agora (como esse ensinamento desafia o homem moderno, o ritmo de vida atual, as redes sociais ou a cultura contemporânea). Sinta-se livre para organizar esses dois aspectos em parágrafos, tópicos ou citações, focando na profundidade e na clareza.

---

## O Ensinamento Prático de Jesus: A Radicalidade do Evangelho
Apresente os desdobramentos práticos e as virtudes extraídas da passagem. Esta seção deve conter ensinamentos essenciais e passos concretos para o fiel aplicar no cotidiano, além de perguntas reflexivas para o exame de consciência. A organização visual desta seção é livre: você pode usar tabelas comparativas, listas ordenadas ou blocos de texto, desde que use negritos nos conceitos-chave para guiar o olhar do leitor.

---

## Oração Acerca do Tema
Comece com: "Em nome do Pai, do Filho e do Espírito Santo. Amém."
Escreva uma oração íntima, sincera e profunda em primeira pessoa do singular (eu). A oração deve passar naturalmente por momentos de reconhecimento da soberania divina, pedido de perdão pelas fraquezas diárias, súplica por força para realizar as renúncias necessárias na vida moderna e intercessão pelas famílias ou pela Igreja. Termine com "Amém."

---

## Gere a meditação para o Evangelho de hoje:
"""

PROMPT_CURIOSIDADES = """
  Atue como um Professor de História da Igreja e Catequista dinâmico. Quero que você crie um texto fascinante, rico em conteúdo e altamente visual sobre o seguinte assunto da fé católica: **{tema}**.

O tom deve ser natural, instigante, que desperte curiosidade no leitor, mantendo a profundidade e a reverência teológica. Não responda como um modelo de IA; comece diretamente no texto.

A estrutura de títulos (H2 e H3) e o uso de negritos devem seguir rigorosamente o modelo abaixo, mas a organização interna do conteúdo (o uso de listas, parágrafos ou blocos de destaque, apenas tabelas que não) fica totalmente a seu critério, utilizando o formato que você considerar mais didático e atraente para o assunto escolhido.

## Mistérios da Fé: [Nome do Assunto Geral]
Abra com uma pergunta provocativa para capturar o leitor e faça uma breve introdução contextualizando como a mentalidade católica sempre utilizou a arte, a história e os símbolos como uma catequese viva. Termine esta introdução com a frase: "Aqui está o resumo rápido para você dominar o assunto hoje:"

---

## O que é (ou o que foram) os [Nome do Assunto]?
Desenvolva a definição técnica, histórica ou conceitual do assunto. Explique a origem desse fato ou tradição e mostre que o objetivo nunca foi puramente estético ou social, mas sim uma chave de leitura para realidades espirituais invisíveis. Organize a explicação da maneira que achar mais clara.

---

## Três Pilares Surpreendentes deste Legado
Apresente exatamente 3 pontos fundamentais sobre o tema. Para cada um dos 3 pontos, você deve criar um subtítulo H3 indicando o nome do item. A forma de expor o fato histórico e o significado espiritual de cada item é livre (em parágrafos separados, listas ou blocos), mas você deve obrigatoriamente usar o termo **O significado:** em negrito para destacar a explicação teológica e sua conexão com a vida de fé.

### [Nome do Primeiro Item]
### [Nome do Segundo Item]
### [Nome do Terceiro Item]

---

## Por que isso importa hoje?
Escreva uma conclusão profunda e de fácil compreensão, consolidando o aprendizado. Mostre como o olhar sacramental da Igreja une o mundo visível ao invisível, e como resgatar esse conhecimento enriquece a nossa experiência de fé no mundo contemporâneo.

---

Gere o texto seguindo rigorosamente o tema fornecido (**{tema}**) e o modelo de estrutura acima.
"""


# =============================================================================
# Conexão com o Neon PostgreSQL (com retry para cold start)
# =============================================================================
def conectar_banco(max_tentativas: int = 3, timeout_inicial: float = 5.0):
    """
    Conecta ao banco de dados Neon PostgreSQL com lógica de retry e backoff
    exponencial para lidar com cold starts do Neon e do Render.
    """
    if not NEON_DATABASE_URL:
        raise RuntimeError("Variável NEON_DATABASE_URL não configurada.")

    tentativa = 0
    ultimo_erro = None

    while tentativa < max_tentativas:
        try:
            logger.info(f"Conectando ao Neon DB (tentativa {tentativa + 1}/{max_tentativas})...")
            conn = psycopg2.connect(
                NEON_DATABASE_URL,
                connect_timeout=int(timeout_inicial),
                options="-c statement_timeout=30000",  # 30s timeout para queries
            )
            conn.autocommit = False
            logger.info("Conexão com o Neon DB estabelecida com sucesso.")
            return conn
        except psycopg2.OperationalError as e:
            ultimo_erro = e
            tentativa += 1
            espera = timeout_inicial * (2 ** (tentativa - 1))  # Backoff exponencial
            logger.warning(
                f"Falha na conexão (tentativa {tentativa}): {e}. "
                f"Aguardando {espera:.1f}s antes de tentar novamente..."
            )
            time.sleep(espera)

    raise RuntimeError(
        f"Não foi possível conectar ao banco após {max_tentativas} tentativas. "
        f"Último erro: {ultimo_erro}"
    )


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
        # Novas tabelas de Autenticação e Sincronização
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
        # Índices para otimizar a sincronização
        cur.execute("CREATE INDEX IF NOT EXISTS idx_favorites_user_sync ON favorites(user_id, updated_at);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_highlights_user_sync ON highlights(user_id, updated_at);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_chats_user_sync ON chats(user_id, updated_at);")

        # Migração segura para colunas de reset de senha
        try:
            cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS reset_token TEXT DEFAULT NULL;")
            cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS reset_token_expires BIGINT DEFAULT NULL;")
        except Exception as me:
            logger.warning(f"Erro ao adicionar colunas de reset em users: {me}")
    conn.commit()
    logger.info("Tabelas verificadas/criadas com sucesso.")


# =============================================================================
# Funções Auxiliares
# =============================================================================
def obter_data_hoje() -> str:
    """Retorna a data de hoje em formato YYYY-MM-DD no fuso de Brasília."""
    agora = datetime.now(ZoneInfo("America/Sao_Paulo"))
    return agora.strftime("%Y-%m-%d")


def obter_data_por_extenso() -> str:
    """Retorna a data de hoje por extenso em português (ex: 'quarta-feira, 18 de junho de 2026')."""
    agora = datetime.now(ZoneInfo("America/Sao_Paulo"))
    dias = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]
    meses = ["janeiro", "fevereiro", "março", "abril", "maio", "junho",
             "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"]
    dia_semana = dias[agora.weekday()]
    mes = meses[agora.month - 1]
    return f"{dia_semana}, {agora.day} de {mes} de {agora.year}"


async def obter_evangelho_do_dia(data: str) -> dict | None:
    """Busca o evangelho do dia a partir da API de liturgia."""
    try:
        partes = data.split("-")
        ano, mes, dia = partes[0], int(partes[1]), int(partes[2])
        url = f"https://liturgia.up.railway.app/v2/?dia={dia}&mes={mes}&ano={ano}"

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            dados = response.json()

        evangelho = None
        leituras = dados.get("leituras", {})
        evangelhos = leituras.get("evangelho", [])
        if evangelhos and len(evangelhos) > 0:
            evangelho = evangelhos[0]

        if evangelho:
            return {
                "referencia": evangelho.get("referencia", ""),
                "titulo": evangelho.get("titulo", ""),
                "texto": evangelho.get("texto", ""),
                "data_literal": dados.get("data", ""),
            }
    except Exception as e:
        logger.error(f"[Liturgia API] Falha ao obter evangelho do dia: {e}")

    return None


async def chamar_gemini(prompt: str) -> str:
    """Chama a API do Gemini usando a biblioteca oficial google-genai."""
    client = get_gemini_client()

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
    )

    texto = response.text
    if not texto:
        raise RuntimeError("A API do Gemini retornou uma resposta vazia.")

    return texto.strip()


# =============================================================================
# FastAPI App
# =============================================================================
app = FastAPI(
    title="API Católica",
    description="API para gerar e servir meditações do Evangelho e curiosidades católicas diárias.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


# =============================================================================
# ENDPOINTS DE AUTENTICAÇÃO
# =============================================================================

@app.post("/api/v1/auth/register")
async def register(req: RegisterRequest):
    email = req.email.strip().lower()
    nome = req.nome.strip()
    password = req.password

    if not email or not nome or not password:
        raise HTTPException(status_code=400, detail="Nome, e-mail e senha são obrigatórios.")

    conn = None
    try:
        conn = conectar_banco()
        with conn.cursor() as cur:
            # Verificar se e-mail já existe
            cur.execute("SELECT id FROM users WHERE email = %s", (email,))
            if cur.fetchone():
                raise HTTPException(status_code=400, detail="E-mail já cadastrado.")

            # Hashing da senha
            p_hash = hash_password(password)

            # Inserir usuário
            cur.execute(
                "INSERT INTO users (nome, email, password_hash) VALUES (%s, %s, %s) RETURNING id, nome, email",
                (nome, email, p_hash)
            )
            user = cur.fetchone()
            conn.commit()

            user_id, u_nome, u_email = user[0], user[1], user[2]
            token = create_access_token(user_id, u_email)

            return {
                "user": {
                    "id": str(user_id),
                    "nome": u_nome,
                    "email": u_email
                },
                "token": token
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Auth Register] Erro no registro: {e}")
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail="Erro interno ao registrar usuário.")
    finally:
        if conn:
            conn.close()


@app.post("/api/v1/auth/login")
async def login(req: LoginRequest):
    email = req.email.strip().lower()
    password = req.password

    if not email or not password:
        raise HTTPException(status_code=400, detail="E-mail e senha são obrigatórios.")

    conn = None
    try:
        conn = conectar_banco()
        with conn.cursor() as cur:
            cur.execute("SELECT id, nome, email, password_hash FROM users WHERE email = %s", (email,))
            user = cur.fetchone()

            if not user or not verify_password(password, user[3]):
                raise HTTPException(status_code=400, detail="Credenciais inválidas.")

            user_id, u_nome, u_email = user[0], user[1], user[2]
            token = create_access_token(user_id, u_email)

            return {
                "user": {
                    "id": str(user_id),
                    "nome": u_nome,
                    "email": u_email
                },
                "token": token
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Auth Login] Erro no login: {e}")
        raise HTTPException(status_code=500, detail="Erro interno ao realizar login.")
    finally:
        if conn:
            conn.close()


@app.put("/api/v1/user/update-email")
async def update_email(req: UpdateEmailRequest, user_id: str = Depends(get_current_user_id)):
    new_email = req.new_email.strip().lower()
    if not new_email:
        raise HTTPException(status_code=400, detail="E-mail inválido.")
        
    conn = None
    try:
        conn = conectar_banco()
        with conn.cursor() as cur:
            # Verificar se já existe esse e-mail em outro usuário
            cur.execute("SELECT id FROM users WHERE email = %s AND id <> %s", (new_email, user_id))
            if cur.fetchone():
                raise HTTPException(status_code=400, detail="E-mail já está em uso por outro usuário.")
                
            cur.execute("UPDATE users SET email = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s", (new_email, user_id))
            conn.commit()
            return {"detail": "E-mail atualizado com sucesso."}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[User Update Email] Erro: {e}")
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail="Erro ao atualizar e-mail.")
    finally:
        if conn:
            conn.close()


@app.put("/api/v1/user/update-password")
async def update_password(req: UpdatePasswordRequest, user_id: str = Depends(get_current_user_id)):
    current_password = req.current_password
    new_password = req.new_password
    
    if not current_password or not new_password:
        raise HTTPException(status_code=400, detail="Senhas atual e nova são obrigatórias.")
        
    if len(new_password) < 6:
        raise HTTPException(status_code=400, detail="A nova senha deve ter no mínimo 6 caracteres.")
        
    conn = None
    try:
        conn = conectar_banco()
        with conn.cursor() as cur:
            cur.execute("SELECT password_hash FROM users WHERE id = %s", (user_id,))
            row = cur.fetchone()
            if not row or not verify_password(current_password, row[0]):
                raise HTTPException(status_code=400, detail="Senha atual incorreta.")
                
            new_hash = hash_password(new_password)
            cur.execute("UPDATE users SET password_hash = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s", (new_hash, user_id))
            conn.commit()
            return {"detail": "Senha atualizada com sucesso."}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[User Update Password] Erro: {e}")
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail="Erro ao atualizar senha.")
    finally:
        if conn:
            conn.close()


@app.post("/api/v1/auth/forgot-password")
async def forgot_password(req: ForgotPasswordRequest):
    email = req.email.strip().lower()
    if not email:
        raise HTTPException(status_code=400, detail="E-mail é obrigatório.")
        
    conn = None
    try:
        conn = conectar_banco()
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM users WHERE email = %s", (email,))
            user = cur.fetchone()
            if not user:
                logger.info(f"[Forgot Password] Solicitação para e-mail inexistente: {email}")
                raise HTTPException(status_code=404, detail="E-mail não cadastrado.")
                
            import random
            import string
            caracteres = string.ascii_letters + string.digits
            nova_senha = "".join(random.choice(caracteres) for _ in range(6))
            
            p_hash = hash_password(nova_senha)
            
            cur.execute(
                "UPDATE users SET password_hash = %s, reset_token = NULL, reset_token_expires = NULL, updated_at = CURRENT_TIMESTAMP WHERE email = %s",
                (p_hash, email)
            )
            conn.commit()
            
            logger.info("*" * 60)
            logger.info(f"[EMAIL SIMULADO] Enviando e-mail para: {email}")
            logger.info(f"Sua nova senha temporária de acesso é: {nova_senha}")
            logger.info("*" * 60)
            
            return {
                "detail": "Uma nova senha temporária foi enviada para o seu e-mail.",
                "temp_password": nova_senha
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Forgot Password] Erro: {e}")
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail="Erro interno ao solicitar recuperação de senha.")
    finally:
        if conn:
            conn.close()


@app.post("/api/v1/auth/reset-password")
async def reset_password(req: ResetPasswordRequest):
    email = req.email.strip().lower()
    token = req.token.strip()
    new_password = req.new_password
    
    if not email or not token or not new_password:
        raise HTTPException(status_code=400, detail="E-mail, código e nova senha são obrigatórios.")
        
    if len(new_password) < 6:
        raise HTTPException(status_code=400, detail="A nova senha deve possuir no mínimo 6 caracteres.")
        
    conn = None
    try:
        conn = conectar_banco()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT reset_token, reset_token_expires FROM users WHERE email = %s",
                (email,)
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=400, detail="E-mail ou código inválido.")
                
            db_token, db_expires = row[0], row[1]
            import time
            now = int(time.time())
            
            if not db_token or db_token != token:
                raise HTTPException(status_code=400, detail="Código de recuperação inválido.")
                
            if db_expires and now > db_expires:
                raise HTTPException(status_code=400, detail="Código de recuperação expirado.")
                
            new_hash = hash_password(new_password)
            cur.execute(
                "UPDATE users SET password_hash = %s, reset_token = NULL, reset_token_expires = NULL, updated_at = CURRENT_TIMESTAMP WHERE email = %s",
                (new_hash, email)
            )
            conn.commit()
            return {"detail": "Senha redefinida com sucesso."}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Reset Password] Erro: {e}")
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail="Erro interno ao redefinir senha.")
    finally:
        if conn:
            conn.close()


# =============================================================================
# ENDPOINT DE SINCRONIZAÇÃO (OFFLINE-FIRST)
# =============================================================================

@app.post("/api/v1/sync")
async def sync(req: SyncRequest, user_id: str = Depends(get_current_user_id)):
    server_timestamp = int(time.time() * 1000)
    conn = None
    try:
        conn = conectar_banco()
        with conn.cursor() as cur:
            # 1. Processar Favoritos do Cliente
            client_fav_ids = set()
            for fav in req.favorites:
                client_fav_ids.add(fav.id)
                # Verificar se já existe no banco remoto
                cur.execute(
                    "SELECT updated_at, is_deleted FROM favorites WHERE id = %s AND user_id = %s",
                    (fav.id, user_id)
                )
                row = cur.fetchone()
                if not row:
                    # Inserir novo
                    cur.execute(
                        """INSERT INTO favorites (id, user_id, type, book_slug, book_title, chapter_id, chapter_name, 
                                                 paragraph_number, paragraph_text, timestamp, group_id, group_range, 
                                                 updated_at, is_deleted)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                        (fav.id, user_id, fav.type, fav.book_slug, fav.book_title, fav.chapter_id, fav.chapter_name,
                         fav.paragraph_number, fav.paragraph_text, fav.timestamp, fav.group_id, fav.group_range,
                         fav.updated_at, fav.is_deleted)
                    )
                else:
                    db_updated_at, db_is_deleted = row[0], row[1]
                    # Se o do cliente for mais recente, atualiza o banco
                    if fav.updated_at > db_updated_at:
                        cur.execute(
                            """UPDATE favorites SET type=%s, book_slug=%s, book_title=%s, chapter_id=%s, chapter_name=%s, 
                                                   paragraph_number=%s, paragraph_text=%s, timestamp=%s, group_id=%s, 
                                                   group_range=%s, updated_at=%s, is_deleted=%s 
                               WHERE id=%s AND user_id=%s""",
                            (fav.type, fav.book_slug, fav.book_title, fav.chapter_id, fav.chapter_name,
                             fav.paragraph_number, fav.paragraph_text, fav.timestamp, fav.group_id, fav.group_range,
                             fav.updated_at, fav.is_deleted, fav.id, user_id)
                        )

            # 2. Processar Grifos (Highlights) do Cliente
            client_hl_ids = set()
            for hl in req.highlights:
                client_hl_ids.add(hl.id)
                cur.execute(
                    "SELECT updated_at, is_deleted FROM highlights WHERE id = %s AND user_id = %s",
                    (hl.id, user_id)
                )
                row = cur.fetchone()
                if not row:
                    # Inserir novo
                    cur.execute(
                        """INSERT INTO highlights (id, user_id, type, book_slug, chapter_id, paragraph_number, 
                                                  start_word_index, end_word_index, highlighted_text, color, 
                                                  timestamp, end_paragraph_number, end_word_index_end, updated_at, is_deleted)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                        (hl.id, user_id, hl.type, hl.book_slug, hl.chapter_id, hl.paragraph_number,
                         hl.start_word_index, hl.end_word_index, hl.highlighted_text, hl.color,
                         hl.timestamp, hl.end_paragraph_number, hl.end_word_index_end, hl.updated_at, hl.is_deleted)
                    )
                else:
                    db_updated_at, db_is_deleted = row[0], row[1]
                    if hl.updated_at > db_updated_at:
                        cur.execute(
                            """UPDATE highlights SET type=%s, book_slug=%s, chapter_id=%s, paragraph_number=%s, 
                                                     start_word_index=%s, end_word_index=%s, highlighted_text=%s, color=%s, 
                                                     timestamp=%s, end_paragraph_number=%s, end_word_index_end=%s, 
                                                     updated_at=%s, is_deleted=%s 
                               WHERE id=%s AND user_id=%s""",
                            (hl.type, hl.book_slug, hl.chapter_id, hl.paragraph_number,
                             hl.start_word_index, hl.end_word_index, hl.highlighted_text, hl.color,
                             hl.timestamp, hl.end_paragraph_number, hl.end_word_index_end, hl.updated_at, hl.is_deleted,
                             hl.id, user_id)
                        )

            # 3. Processar Chats do Cliente
            client_chat_ids = set()
            chats_payload = req.chats or []
            for chat in chats_payload:
                client_chat_ids.add(chat.id)
                cur.execute(
                    "SELECT updated_at, is_deleted FROM chats WHERE id = %s AND user_id = %s",
                    (chat.id, user_id)
                )
                row = cur.fetchone()
                if not row:
                    cur.execute(
                        """INSERT INTO chats (id, user_id, title, created_at, updated_at, messages_json, is_deleted)
                           VALUES (%s, %s, %s, %s, %s, %s, %s)""",
                        (chat.id, user_id, chat.title, chat.created_at, chat.updated_at, chat.messages_json, chat.is_deleted)
                    )
                else:
                    db_updated_at, db_is_deleted = row[0], row[1]
                    if chat.updated_at > db_updated_at:
                        cur.execute(
                            """UPDATE chats SET title=%s, created_at=%s, updated_at=%s, messages_json=%s, is_deleted=%s
                               WHERE id=%s AND user_id=%s""",
                            (chat.title, chat.created_at, chat.updated_at, chat.messages_json, chat.is_deleted, chat.id, user_id)
                        )

            # 4. Obter alterações do banco para o Cliente (novidades desde a última data de sync do cliente)
            # Apenas registros onde updated_at > last_sync_timestamp e que não foram enviados pelo cliente agora
            
            # Buscar favoritos atualizados
            query_fav = """
                SELECT id, type, book_slug, book_title, chapter_id, chapter_name, paragraph_number, 
                       paragraph_text, timestamp, group_id, group_range, updated_at, is_deleted
                FROM favorites 
                WHERE user_id = %s AND updated_at > %s
            """
            cur.execute(query_fav, (user_id, req.last_sync_timestamp))
            db_favorites = cur.fetchall()
            
            server_favorites = []
            for row in db_favorites:
                if row[0] not in client_fav_ids:
                    server_favorites.append({
                        "id": row[0],
                        "type": row[1],
                        "book_slug": row[2],
                        "book_title": row[3],
                        "chapter_id": row[4],
                        "chapter_name": row[5],
                        "paragraph_number": row[6],
                        "paragraph_text": row[7],
                        "timestamp": int(row[8]),
                        "group_id": row[9],
                        "group_range": row[10],
                        "updated_at": int(row[11]),
                        "is_deleted": bool(row[12])
                    })
 
            # Buscar grifos atualizados
            query_hl = """
                SELECT id, type, book_slug, chapter_id, paragraph_number, start_word_index, 
                       end_word_index, highlighted_text, color, timestamp, end_paragraph_number, 
                       end_word_index_end, updated_at, is_deleted
                FROM highlights 
                WHERE user_id = %s AND updated_at > %s
            """
            cur.execute(query_hl, (user_id, req.last_sync_timestamp))
            db_highlights = cur.fetchall()
            
            server_highlights = []
            for row in db_highlights:
                if row[0] not in client_hl_ids:
                    server_highlights.append({
                        "id": row[0],
                        "type": row[1],
                        "book_slug": row[2],
                        "chapter_id": row[3],
                        "paragraph_number": row[4],
                        "start_word_index": row[5],
                        "end_word_index": row[6],
                        "highlighted_text": row[7],
                        "color": row[8],
                        "timestamp": int(row[9]),
                        "end_paragraph_number": row[10],
                        "end_word_index_end": row[11],
                        "updated_at": int(row[12]),
                        "is_deleted": bool(row[13])
                    })

            # Buscar chats atualizados
            query_chat = """
                SELECT id, title, created_at, updated_at, messages_json, is_deleted
                FROM chats 
                WHERE user_id = %s AND updated_at > %s
            """
            cur.execute(query_chat, (user_id, req.last_sync_timestamp))
            db_chats = cur.fetchall()
            
            server_chats = []
            for row in db_chats:
                if row[0] not in client_chat_ids:
                    server_chats.append({
                        "id": row[0],
                        "title": row[1],
                        "created_at": int(row[2]),
                        "updated_at": int(row[3]),
                        "messages_json": row[4],
                        "is_deleted": bool(row[5])
                    })
 
            # Efetivar transação
            conn.commit()
 
            return {
                "server_timestamp": server_timestamp,
                "changes": {
                    "favorites": server_favorites,
                    "highlights": server_highlights,
                    "chats": server_chats
                }
            }
    except Exception as e:
        logger.error(f"[Sync Engine] Erro durante sincronização: {e}")
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail=f"Erro interno de sincronização: {str(e)}")
    finally:
        if conn:
            conn.close()


@app.on_event("startup")
def startup_event():
    """Garante que as tabelas existam ao iniciar a aplicação."""
    logger.info("Inicializando API Católica...")
    try:
        conn = conectar_banco()
        garantir_tabelas(conn)
        conn.close()
    except Exception as e:
        logger.error(f"Erro ao inicializar o banco de dados: {e}")
        # Não levanta exceção para permitir que o Render conclua o deploy


# -------------------------------------------------------------------------
# POST /api/v1/gerar-conteudo
# -------------------------------------------------------------------------
@app.post("/api/v1/gerar-conteudo")
async def gerar_conteudo():
    data_hoje = obter_data_hoje()
    logger.info(f"[Gerar Conteúdo] Iniciando para a data: {data_hoje}")

    conn = None
    try:
        conn = conectar_banco()

        # 1. Verificar se já existem registros para hoje
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM meditacoes_evangelho WHERE data = %s", (data_hoje,))
            tem_meditacao = cur.fetchone() is not None

            cur.execute("SELECT 1 FROM curiosidades_catolicas WHERE data = %s", (data_hoje,))
            tem_curiosidade = cur.fetchone() is not None

            cur.execute("SELECT 1 FROM santos_do_dia WHERE data = %s", (data_hoje,))
            tem_santo = cur.fetchone() is not None

            cur.execute("SELECT 1 FROM liturgias_diarias WHERE data = %s", (data_hoje,))
            tem_liturgia = cur.fetchone() is not None

        if tem_meditacao and tem_curiosidade and tem_santo and tem_liturgia:
            logger.info("[Gerar Conteúdo] Todos os conteúdos (meditação, curiosidade, santo, liturgia) já existem para hoje. Pulando.")
            return {
                "message": "Registros já atualizados para hoje.",
                "date": data_hoje,
                "actions": {
                    "meditacao": "skipped",
                    "curiosidade": "skipped",
                    "santo": "skipped",
                    "liturgia": "skipped"
                },
            }

        # 2. Preparar as tarefas de geração em paralelo
        tarefas = []
        texto_meditacao = ""
        texto_curiosidade = ""
        santo_data = None
        liturgia_data = None

        if not tem_meditacao:
            logger.info("[Gerar Conteúdo] Preparando geração da meditação...")

            async def gerar_meditacao():
                nonlocal texto_meditacao
                evangelho = await obter_evangelho_do_dia(data_hoje)
                data_extenso = obter_data_por_extenso()

                prompt = PROMPT_EVANGELHO
                if evangelho:
                    logger.info(f"[Gerar Conteúdo] Evangelho obtido: {evangelho['referencia']}")
                    prompt += (
                        f" Passagem: {evangelho['referencia']} ({evangelho['titulo']}).\n\n"
                        f"Data de hoje: {data_extenso}.\n\n"
                        f"Texto do Evangelho:\n\"{evangelho['texto']}\""
                    )
                else:
                    logger.warning("[Gerar Conteúdo] Não foi possível obter o Evangelho. Usando data.")
                    prompt += f" correspondente à data: {data_extenso}."

                texto_meditacao = await chamar_gemini(prompt)

            tarefas.append(gerar_meditacao())

        if not tem_curiosidade:
            logger.info("[Gerar Conteúdo] Preparando geração da curiosidade...")

            async def gerar_curiosidade():
                nonlocal texto_curiosidade
                base_dir = os.path.dirname(os.path.abspath(__file__))
                temas_file = os.path.join(base_dir, "Temas_Curiosidades.txt")
                tema_escolhido = "um assunto católico aleatório e fascinante"

                try:
                    if os.path.exists(temas_file):
                        with open(temas_file, "r", encoding="utf-8") as f:
                            temas = [linha.strip() for linha in f if linha.strip()]
                        if temas:
                            tema_escolhido = random.choice(temas)
                            logger.info(f"[Gerar Conteúdo] Tema de curiosidade escolhido do arquivo: '{tema_escolhido}'")
                        else:
                            logger.warning("[Gerar Conteúdo] Arquivo de temas de curiosidades está vazio. Usando fallback.")
                    else:
                        logger.warning(f"[Gerar Conteúdo] Arquivo {temas_file} não encontrado. Usando fallback.")
                except Exception as e:
                    logger.error(f"[Gerar Conteúdo] Erro ao ler arquivo de temas de curiosidades: {e}. Usando fallback.")

                prompt_formatado = PROMPT_CURIOSIDADES.format(tema=tema_escolhido)
                texto_curiosidade = await chamar_gemini(prompt_formatado)

            tarefas.append(gerar_curiosidade())

        if not tem_santo:
            logger.info("[Gerar Conteúdo] Preparando geração/scrape do Santo do Dia...")

            async def gerar_santo():
                nonlocal santo_data
                santo_data = await extrair_santo_do_dia_por_data(data_hoje)

            tarefas.append(gerar_santo())

        if not tem_liturgia:
            logger.info("[Gerar Conteúdo] Preparando scrape da Liturgia Diária...")

            async def gerar_liturgia():
                nonlocal liturgia_data
                liturgia_data = await extrair_liturgia_diaria_por_data(data_hoje)

            tarefas.append(gerar_liturgia())

        # 3. Executar chamadas em paralelo
        await asyncio.gather(*tarefas)
        logger.info("[Gerar Conteúdo] Conteúdos processados com sucesso.")

        # 4. Salvar no banco de dados Neon
        with conn.cursor() as cur:
            if texto_meditacao:
                cur.execute(
                    """INSERT INTO meditacoes_evangelho (conteudo, data)
                       VALUES (%s, %s)
                       ON CONFLICT (data)
                       DO UPDATE SET conteudo = EXCLUDED.conteudo""",
                    (texto_meditacao, data_hoje),
                )

            if texto_curiosidade:
                cur.execute(
                    """INSERT INTO curiosidades_catolicas (conteudo, data)
                       VALUES (%s, %s)
                       ON CONFLICT (data)
                       DO UPDATE SET conteudo = EXCLUDED.conteudo""",
                    (texto_curiosidade, data_hoje),
                )

            if santo_data:
                cur.execute(
                    """INSERT INTO santos_do_dia (conteudo, data)
                       VALUES (%s, %s)
                       ON CONFLICT (data)
                       DO UPDATE SET conteudo = EXCLUDED.conteudo""",
                    (json.dumps(santo_data, ensure_ascii=False), data_hoje),
                )

            if liturgia_data:
                cur.execute(
                    """INSERT INTO liturgias_diarias (conteudo, data)
                       VALUES (%s, %s)
                       ON CONFLICT (data)
                       DO UPDATE SET conteudo = EXCLUDED.conteudo""",
                    (json.dumps(liturgia_data, ensure_ascii=False), data_hoje),
                )

        conn.commit()
        logger.info("[Gerar Conteúdo] Todos os registros salvos com sucesso no Neon DB.")

        return {
            "message": "Geração e salvamento unificados concluídos com sucesso.",
            "date": data_hoje,
            "actions": {
                "meditacao": "generated" if not tem_meditacao else "skipped",
                "curiosidade": "generated" if not tem_curiosidade else "skipped",
                "santo": "generated" if not tem_santo else "skipped",
                "liturgia": "generated" if not tem_liturgia else "skipped",
            },
        }

    except Exception as e:
        logger.error(f"[Gerar Conteúdo] Erro: {e}")
        if conn:
            conn.rollback()
        raise HTTPException(status_code=500, detail=f"Erro ao gerar conteúdo: {str(e)}")
    finally:
        if conn:
            conn.close()


# -------------------------------------------------------------------------
# GET /api/v1/meditacao
# -------------------------------------------------------------------------
@app.get("/api/v1/meditacao")
async def obter_meditacao(date: str = Query(default=None, description="Data no formato YYYY-MM-DD")):
    """Retorna a meditação do Evangelho para a data informada (retorna 404 se não houver dados)."""
    data_alvo = date or obter_data_hoje()
    conn = None

    try:
        conn = conectar_banco()

        with conn.cursor() as cur:
            # 1. Buscar pela data solicitada
            cur.execute(
                "SELECT conteudo, data FROM meditacoes_evangelho WHERE data = %s",
                (data_alvo,),
            )
            row = cur.fetchone()

            if row:
                return {"markdown": row[0], "date": str(row[1]), "isLatestFallback": False}

        raise HTTPException(status_code=404, detail="Nenhuma meditação disponível para a data especificada.")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[API Meditação] Erro: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao consultar meditação: {str(e)}")
    finally:
        if conn:
            conn.close()


# -------------------------------------------------------------------------
# GET /api/v1/curiosidades
# -------------------------------------------------------------------------
@app.get("/api/v1/curiosidades")
async def obter_curiosidades(date: str = Query(default=None, description="Data no formato YYYY-MM-DD")):
    """Retorna a curiosidade católica para a data informada (retorna 404 se não houver dados)."""
    data_alvo = date or obter_data_hoje()
    conn = None

    try:
        conn = conectar_banco()

        with conn.cursor() as cur:
            # 1. Buscar pela data solicitada
            cur.execute(
                "SELECT conteudo, data FROM curiosidades_catolicas WHERE data = %s",
                (data_alvo,),
            )
            row = cur.fetchone()

            if row:
                return {"markdown": row[0], "date": str(row[1]), "isLatestFallback": False}

        raise HTTPException(status_code=404, detail="Nenhuma curiosidade disponível para a data especificada.")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[API Curiosidades] Erro: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao consultar curiosidades: {str(e)}")
    finally:
        if conn:
            conn.close()


# -------------------------------------------------------------------------
# POST /api/v1/chat
# -------------------------------------------------------------------------
@app.post("/api/v1/chat")
async def proxy_chat(
    payload: dict,
    x_sanctus_token: str = Header(default=None, alias="x-sanctus-token")
):
    """
    Proxy seguro para a API do Magisterium AI.
    Valida o token compartilhado 'x-sanctus-token' antes de fazer o redirecionamento.
    """
    # 1. Validar se o token do App foi configurado no servidor
    # Se estiver configurado, validar se o cabeçalho bate
    if SANCTUS_APP_TOKEN and x_sanctus_token != SANCTUS_APP_TOKEN:
        logger.warning(f"[Proxy Chat] Acesso não autorizado. Header: {x_sanctus_token}")
        raise HTTPException(
            status_code=401,
            detail="Acesso não autorizado: Token inválido ou ausente."
        )

    # 2. Validar se a chave do Magisterium AI está configurada no servidor
    if not MAGISTERIUM_API_KEY:
        logger.error("[Proxy Chat] Chave MAGISTERIUM_API_KEY não configurada no servidor.")
        raise HTTPException(
            status_code=500,
            detail="Chave de API do Magisterium AI não configurada no servidor."
        )

    url = "https://www.magisterium.com/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {MAGISTERIUM_API_KEY}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, json=payload, headers=headers)
            
            if not response.is_success:
                logger.error(f"[Proxy Chat] Erro do Magisterium AI: {response.status_code} - {response.text}")
                try:
                    error_detail = response.json()
                except Exception:
                    error_detail = response.text
                
                raise HTTPException(
                    status_code=response.status_code,
                    detail=error_detail
                )
            
            return response.json()
    except httpx.RequestError as e:
        logger.error(f"[Proxy Chat] Erro de rede: {e}")
        raise HTTPException(
            status_code=503,
            detail=f"Erro de conexão com o Magisterium AI: {str(e)}"
        )
    except Exception as e:
        logger.error(f"[Proxy Chat] Erro inesperado: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Erro interno no proxy: {str(e)}"
        )


# =============================================================================
# SCRAPER E ROTAS DO SANTO DO DIA
# =============================================================================

def strip_html_comments(text: str) -> str:
    if not text:
        return ""
    return re.sub(r'<!--[\s\S]*?-->', '', text)


def decode_html_entities(text: str) -> str:
    if not text:
        return ""
    text = text.replace('&nbsp;', ' ').replace('&amp;', '&').replace('&quot;', '"').replace('&#39;', "'")
    text = text.replace('&lt;', '<').replace('&gt;', '>')
    # Tratar referências numéricas: &#(\d+);
    text = re.sub(r'&#(\d+);', lambda m: chr(int(m.group(1))), text)
    # Tratar referências hexadecimais: &#x([0-9a-fA-F]+);
    text = re.sub(r'&#x([0-9a-fA-F]+);', lambda m: chr(int(m.group(1), 16)), text)
    return text


def strip_tags(html: str) -> str:
    if not html:
        return ""
    # Substituir br por newline
    html = re.sub(r'<\s*br\s*/?\s*>', '\n', html, flags=re.IGNORECASE)
    # Substituir fim de p por duplo newline
    html = re.sub(r'<\s*/\s*p\s*>', '\n\n', html, flags=re.IGNORECASE)
    # Remover outras tags
    html = re.sub(r'<[^>]+>', '', html)
    # Decodificar entidades HTML
    html = decode_html_entities(html)
    # Normalizar quebras de linha
    html = re.sub(r'\r', '', html)
    html = re.sub(r'\n{3,}', '\n\n', html)
    return html.strip()


def extract_element_inner_html(html: str, open_tag_re_str: str) -> str:
    match = re.search(open_tag_re_str, html, re.IGNORECASE)
    if not match:
        return ""
    
    tag_match = re.match(r'<([a-z0-9]+)', match.group(0), re.IGNORECASE)
    if not tag_match:
        return ""
    tag = tag_match.group(1).lower()
    
    open_tag_end = match.end()
    tag_re = re.compile(rf'</?{tag}\b', re.IGNORECASE)
    
    depth = 1
    for m in tag_re.finditer(html, open_tag_end):
        is_closing = m.group(0).startswith('</')
        if is_closing:
            depth -= 1
        else:
            depth += 1
            
        if depth == 0:
            return html[open_tag_end:m.start()]
            
    return ""


def choose_best_image(entry_html: str) -> str:
    candidates = re.findall(r'<img[^>]*src=["\']([^"\']+)["\'][^>]*>', entry_html, re.IGNORECASE)
    
    def is_bad(src: str) -> bool:
        s = src.lower()
        return 'icon-x-ext' in s or 'device-liturgia' in s or 'pedido-thumb' in s
        
    def is_good(src: str) -> bool:
        s = src.lower()
        return any(ext in s for ext in ['.jpg', '.jpeg', '.png', '.webp']) or 'uploads' in s or 'cnimages' in s
        
    good = [src for src in candidates if not is_bad(src) and is_good(src)]
    if good:
        return good[0]
        
    ok = [src for src in candidates if not is_bad(src)]
    return ok[0] if ok else None


def normalize_spaces(text: str) -> str:
    if not text:
        return ""
    text = text.replace('\u00A0', ' ')
    text = re.sub(r'[ \t]{2,}', ' ', text)
    text = re.sub(r'\n[ \t]+', '\n', text)
    text = re.sub(r'[ \t]+\n', '\n', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def should_skip_text(text: str) -> bool:
    cleaned = normalize_spaces(text)
    if not cleaned or cleaned in ['.', '…', '-->', '->']:
        return True
    upper = cleaned.upper()
    return any(term in upper for term in ['COMPARTILHE NO', 'AJUDE A CANCAO NOVA', 'PEDIDO DE ORACAO', 'APLICATIVO LITURGIA'])


def is_bold_only_paragraph(inner_html: str) -> bool:
    s = inner_html.strip()
    if not s:
        return False
    return bool(re.match(r'^(?:<span\b[^>]*>\s*)*<(strong|b)\b[^>]*>[\s\S]*?</\1>\s*(?:</span>\s*)*$', s, re.IGNORECASE))


def normalize_search_key(text: str) -> str:
    import unicodedata
    if not text:
        return ""
    text_normalized = unicodedata.normalize('NFD', text)
    text_no_accents = "".join(c for c in text_normalized if unicodedata.category(c) != 'Mn')
    return text_no_accents.lower()


def is_outros_santos_text(text: str) -> bool:
    n = normalize_search_key(text)
    return 'outros' in n and ('santos' in n or 'beatos' in n)


def is_footer_text(text: str) -> bool:
    n = normalize_search_key(text).strip()
    return n in ['fontes:', 'fontes']


def find_other_saints_section_index(entry_html: str) -> int:
    re_tag = re.compile(r'<(h2|h3|h4|p|strong|b)\b[^>]*>([\s\S]*?)</\1>', re.IGNORECASE)
    for match in re_tag.finditer(entry_html):
        if is_outros_santos_text(strip_tags(match.group(2))):
            return match.start()
    return -1


def find_footer_section_index(entry_html: str) -> int:
    re_tag = re.compile(r'<(h2|h3|h4|p|strong|b)\b[^>]*>([\s\S]*?)</\1>', re.IGNORECASE)
    for match in re_tag.finditer(entry_html):
        if is_footer_text(strip_tags(match.group(2))):
            return match.start()
    return -1


def extract_content_blocks(entry_html: str) -> list:
    blocks = []
    
    other_idx = find_other_saints_section_index(entry_html)
    footer_idx = find_footer_section_index(entry_html)
    
    end_idx = -1
    if other_idx >= 0 and footer_idx >= 0:
        end_idx = min(other_idx, footer_idx)
    elif other_idx >= 0:
        end_idx = other_idx
    elif footer_idx >= 0:
        end_idx = footer_idx
        
    html = entry_html[:end_idx] if end_idx >= 0 else entry_html
    
    element_re = re.compile(r'<(p|h2|h3|h4|blockquote|ul|ol|strong|b)\b[^>]*>([\s\S]*?)</\1>', re.IGNORECASE)
    
    for match in element_re.finditer(html):
        tag = match.group(1).lower()
        inner = match.group(2)
        
        plain_text = strip_tags(inner)
        if is_outros_santos_text(plain_text) or is_footer_text(plain_text):
            break
            
        if tag in ['ul', 'ol']:
            items_raw = re.findall(r'<li[^>]*>([\s\S]*?)</li>', inner, re.IGNORECASE)
            items = [normalize_spaces(strip_tags(item)) for item in items_raw]
            items = [item for item in items if item and not should_skip_text(item)]
            if items:
                blocks.append({"type": tag, "items": items})
            continue
            
        if tag in ['strong', 'b']:
            cleaned = normalize_spaces(plain_text)
            if cleaned and not should_skip_text(cleaned):
                blocks.append({"type": "h3", "text": cleaned})
            continue
            
        if tag == 'p':
            if is_bold_only_paragraph(inner):
                cleaned = normalize_spaces(plain_text)
                if cleaned and not should_skip_text(cleaned):
                    blocks.append({"type": "h3", "text": cleaned})
                continue
                
            bold_re = re.compile(r'<(strong|b)\b[^>]*>([\s\S]*?)</\1>', re.IGNORECASE)
            last_index = 0
            has_bold = False
            
            for bm in bold_re.finditer(inner):
                has_bold = True
                before_html = inner[last_index:bm.start()]
                cleaned_before = normalize_spaces(strip_tags(before_html))
                if cleaned_before and not should_skip_text(cleaned_before):
                    blocks.append({"type": "p", "text": cleaned_before})
                    
                bold_html = bm.group(2)
                cleaned_bold = normalize_spaces(strip_tags(bold_html))
                if cleaned_bold and not should_skip_text(cleaned_bold):
                    blocks.append({"type": "h3", "text": cleaned_bold})
                    
                last_index = bm.end()
                
            if has_bold:
                after_html = inner[last_index:]
                cleaned_after = normalize_spaces(strip_tags(after_html))
                if cleaned_after and not should_skip_text(cleaned_after):
                    blocks.append({"type": "p", "text": cleaned_after})
                continue
                
            cleaned = normalize_spaces(plain_text)
            if cleaned and not should_skip_text(cleaned):
                blocks.append({"type": "p", "text": cleaned})
            continue
            
        cleaned = normalize_spaces(plain_text)
        if cleaned and not should_skip_text(cleaned):
            blocks.append({"type": tag, "text": cleaned})
            
    return blocks if blocks else None


def extract_balanced_outer_html_from(html: str, tag_name: str, start_index: int = 0) -> str:
    slice_html = html[start_index:]
    open_match = re.search(rf'<{tag_name}\b[^>]*>', slice_html, re.IGNORECASE)
    if not open_match:
        return None
        
    absolute_open_start = start_index + open_match.start()
    open_tag_end = absolute_open_start + len(open_match.group(0))
    
    tag_re = re.compile(rf'</?{tag_name}\b', re.IGNORECASE)
    depth = 1
    
    for mm in tag_re.finditer(html, open_tag_end):
        is_closing = mm.group(0).startswith('</')
        if is_closing:
            depth -= 1
        else:
            depth += 1
            
        if depth == 0:
            close_start = mm.start()
            close_end = html.find('>', close_start)
            if close_end == -1:
                return None
            return html[absolute_open_start:close_end + 1]
            
    return None


def extract_other_saints(entry_html: str) -> list:
    other_idx = find_other_saints_section_index(entry_html)
    footer_idx = find_footer_section_index(entry_html)
    
    candidates = []
    
    if other_idx >= 0:
        other_slice = entry_html[other_idx:footer_idx] if footer_idx >= 0 and footer_idx > other_idx else entry_html[other_idx:]
        ul_outer = extract_balanced_outer_html_from(other_slice, 'ol') or extract_balanced_outer_html_from(other_slice, 'ul')
        
        if ul_outer:
            items_raw = re.findall(r'<li[^>]*>([\s\S]*?)</li>', ul_outer, re.IGNORECASE)
            items = [normalize_spaces(strip_tags(item)) for item in items_raw]
            items = [item for item in items if item]
            if items:
                return items
                
    list_re = re.compile(r'<(ul|ol)\b[^>]*>([\s\S]*?)</\1>', re.IGNORECASE)
    best_score = -1
    best_items = None
    
    for mm in list_re.finditer(entry_html):
        outer = mm.group(0)
        inner = mm.group(2)
        items_raw = re.findall(r'<li[^>]*>([\s\S]*?)</li>', inner, re.IGNORECASE)
        items = [normalize_spaces(strip_tags(item)) for item in items_raw]
        items = [item for item in items if item]
        if len(items) < 3:
            continue
            
        starts_with_em = sum(1 for i in items if re.match(r'^em\s+', i, re.IGNORECASE))
        has_dagger = sum(1 for i in items if '†' in i)
        score = len(items) + starts_with_em * 2 + has_dagger
        
        if score > best_score:
            best_score = score
            best_items = items
            
    if best_items:
        candidates.extend(best_items)
        
    return candidates if candidates else None


def extract_image_caption(entry_html: str, image_url: str) -> str:
    if not image_url:
        return None
    try:
        img_idx = entry_html.find(image_url)
        if img_idx < 0:
            return None
            
        p_close_idx = entry_html.find('</p>', img_idx)
        if p_close_idx < 0:
            return None
            
        after = entry_html[p_close_idx + 4 : p_close_idx + 1004]
        next_p = re.match(r'^\s*<p[^>]*>([\s\S]*?)</p>', after, re.IGNORECASE)
        if not next_p:
            return None
            
        inner = next_p.group(1)
        if not re.search(r'<span\b', inner, re.IGNORECASE):
            return None
            
        if re.match(r'^\s*<strong\b', inner, re.IGNORECASE):
            return None
            
        text = strip_tags(inner).strip()
        if not text or len(text) > 200:
            return None
            
        return text
    except Exception:
        return None


def get_month_name_pt(month_num: int) -> str:
    months = {
        1: "janeiro", 2: "fevereiro", 3: "marco", 4: "abril",
        5: "maio", 6: "junho", 7: "julho", 8: "agosto",
        9: "setembro", 10: "outubro", 11: "novembro", 12: "dezembro"
    }
    return months.get(month_num, "")


def get_month_abbrev_pt(month_num: int) -> str:
    abbrevs = {
        1: "jan", 2: "fev", 3: "mar", 4: "abr",
        5: "mai", 6: "jun", 7: "jul", 8: "ago",
        9: "set", 10: "out", 11: "nov", 12: "dez"
    }
    return abbrevs.get(month_num, "")


async def extrair_santo_do_dia_por_data(target_date: str, fallback_home: bool = True) -> dict:
    """
    Executa o scraping do Santo do Dia para a data especificada (no formato YYYY-MM-DD).
    Retorna o dicionário com a estrutura de dados necessária.
    """
    try:
        dt = datetime.strptime(target_date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Formato de data inválido. Use YYYY-MM-DD.")
        
    day_str = str(dt.day)
    month_name = get_month_name_pt(dt.month)
    month_abbrev = get_month_abbrev_pt(dt.month)
    year_str = str(dt.year)
    
    url = f"https://santo.cancaonova.com/santo/{day_str}-de-{month_name}/"
    
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.get(url, headers={
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'pt-BR,pt;q=0.9,en;q=0.6',
        })
        if response.status_code == 404:
            if not fallback_home:
                raise HTTPException(status_code=404, detail="Santo do dia não disponível para a data especificada.")
            response = await client.get("https://santo.cancaonova.com/", headers={
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'pt-BR,pt;q=0.9,en;q=0.6',
            })
        
        response.raise_for_status()
            
    html = strip_html_comments(response.text)
    
    title_match = re.search(r'<h1[^>]*class=["\'][^"\']*entry-title[^"\']*["\'][^>]*>([\s\S]*?)</h1>', html, re.IGNORECASE)
    title = strip_tags(title_match.group(1)) if title_match else "Santo do Dia"
    
    entry_inner = extract_element_inner_html(html, r'<([a-z0-9]+)[^>]*class=["\'][^"\']*entry-content[^"\']*["\'][^>]*>')
    
    image = choose_best_image(entry_inner) if entry_inner else None
    image_caption = extract_image_caption(entry_inner, image) if entry_inner and image else None
    content_blocks = extract_content_blocks(entry_inner) if entry_inner else None
    full_text = strip_tags(entry_inner) if entry_inner else None
    
    if image_caption and content_blocks:
        caption_norm = normalize_search_key(image_caption)
        content_blocks = [b for b in content_blocks if not ('text' in b and normalize_search_key(b['text']) == caption_norm)]
        if not content_blocks:
            content_blocks = None
            
    outros_santos = extract_other_saints(entry_inner) if entry_inner else None
    
    return {
        "objective": "A API_LITURGIA_DIARIA visa disponibilizar via api as leituras para facilitar a criação de aplicações que almejam a evangelização.",
        "source": "Canção Nova",
        "today": {
            "day": day_str,
            "month": month_abbrev,
            "year": year_str,
            "title": title,
            "image": image,
            "image_caption": image_caption,
            "content_blocks": content_blocks,
            "full_text": full_text,
            "outros_santos": outros_santos
        }
    }


async def extrair_liturgia_diaria_por_data(target_date: str) -> dict:
    """
    Busca a liturgia diária da API externa (https://liturgia.up.railway.app/v2/)
    para a data informada (YYYY-MM-DD) e retorna o JSON estruturado.
    """
    try:
        dt = datetime.strptime(target_date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Formato de data inválido. Use YYYY-MM-DD.")

    dia = str(dt.day)
    mes = str(dt.month)
    ano = str(dt.year)

    url = f"https://liturgia.up.railway.app/v2/?dia={dia}&mes={mes}&ano={ano}"
    logger.info(f"[Liturgia Diária] Buscando da API externa: {url}")

    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            response = await client.get(url)
            response.raise_for_status()
            liturgy_data = response.json()
            return liturgy_data
        except Exception as e:
            logger.error(f"[Liturgia Diária] Erro ao buscar dados externos: {e}")
            raise HTTPException(
                status_code=503,
                detail=f"Não foi possível obter a liturgia da API externa: {str(e)}"
            )


@app.get("/api/v1/liturgia")
async def obter_liturgia_diaria(
    date: str = Query(default=None, description="Data no formato YYYY-MM-DD")
):
    """
    Retorna a Liturgia Diária para a data informada (ou hoje) a partir do Neon DB.
    Se não houver registro para a data, gera-o dinamicamente consultando a API externa.
    """
    data_alvo = date or obter_data_hoje()
    conn = None
    try:
        conn = conectar_banco()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT conteudo FROM liturgias_diarias WHERE data = %s",
                (data_alvo,)
            )
            row = cur.fetchone()
            if row:
                return json.loads(row[0])
                
        logger.warning(f"[Liturgia Diária] Nenhuma liturgia encontrada no Neon para a data {data_alvo}. Gerando dinamicamente.")
        try:
            liturgia_gerada = await extrair_liturgia_diaria_por_data(data_alvo)
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO liturgias_diarias (conteudo, data)
                       VALUES (%s, %s)
                       ON CONFLICT (data)
                       DO UPDATE SET conteudo = EXCLUDED.conteudo""",
                    (json.dumps(liturgia_gerada, ensure_ascii=False), data_alvo)
                )
            conn.commit()
            return liturgia_gerada
        except Exception as scrap_err:
            logger.error(f"[Liturgia Diária] Falha ao obter dinamicamente para {data_alvo}: {scrap_err}.")
            raise HTTPException(status_code=404, detail="Liturgia diária não disponível para a data especificada.")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Liturgia Diária API] Erro ao consultar: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao obter liturgia diária: {str(e)}")
    finally:
        if conn:
            conn.close()


@app.get("/api/v1/santo-do-dia")
async def obter_santo_do_dia(
    date: str = Query(default=None, description="Data no formato YYYY-MM-DD")
):
    """
    Retorna o Santo do Dia para a data informada (ou hoje) a partir do Neon DB.
    Se não houver registro para a data, gera-o dinamicamente realizando scraping.
    """
    data_alvo = date or obter_data_hoje()
    data_hoje = obter_data_hoje()
    conn = None
    try:
        conn = conectar_banco()
        with conn.cursor() as cur:
            # 1. Verificar se tem no banco na data selecionada (data_alvo)
            cur.execute(
                "SELECT conteudo, data FROM santos_do_dia WHERE data = %s",
                (data_alvo,)
            )
            row = cur.fetchone()
            if row:
                santo_json = json.loads(row[0])
                santo_json["isLatestFallback"] = False
                santo_json["date"] = str(row[1])
                return santo_json
                
        # 2. Não está no banco. Tenta gerar dinamicamente
        logger.warning(f"[Santo do Dia] Nenhum santo encontrado no Neon para a data {data_alvo}. Gerando dinamicamente.")
        try:
            # Só faz fallback_home se for a data de hoje real
            santo_gerado = await extrair_santo_do_dia_por_data(data_alvo, fallback_home=(data_alvo == data_hoje))
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO santos_do_dia (conteudo, data)
                       VALUES (%s, %s)
                       ON CONFLICT (data)
                       DO UPDATE SET conteudo = EXCLUDED.conteudo""",
                    (json.dumps(santo_gerado, ensure_ascii=False), data_alvo)
                )
            conn.commit()
            santo_gerado["isLatestFallback"] = False
            santo_gerado["date"] = data_alvo
            return santo_gerado
        except HTTPException as scrap_err:
            if scrap_err.status_code == 404:
                logger.warning(f"[Santo do Dia] Registro inexistente para a data {data_alvo}. Verificando hoje real ({data_hoje}).")
                # Se der 404 para a data selecionada (que não é hoje), verifica se hoje real já tem registro no banco
                with conn.cursor() as cur:
                    cur.execute("SELECT id FROM santos_do_dia WHERE data = %s", (data_hoje,))
                    tem_hoje = cur.fetchone()
                    if not tem_hoje:
                        # Se não tem hoje real, tenta extrair e salvar para o dia de hoje real
                        try:
                            santo_hoje = await extrair_santo_do_dia_por_data(data_hoje, fallback_home=True)
                            cur.execute(
                                """INSERT INTO santos_do_dia (conteudo, data)
                                   VALUES (%s, %s)
                                   ON CONFLICT (data)
                                   DO UPDATE SET conteudo = EXCLUDED.conteudo""",
                                (json.dumps(santo_hoje, ensure_ascii=False), data_hoje)
                            )
                            conn.commit()
                            logger.info(f"[Santo do Dia] Criado registro de hoje real ({data_hoje}) na checagem de fallback.")
                        except Exception as e_hoje:
                            logger.error(f"[Santo do Dia] Falha ao criar hoje real: {e_hoje}")
                
                # Para o usuário que solicitou a data alvo diferente de hoje, retorna 404
                raise HTTPException(status_code=404, detail="Não existem registros do Santo do Dia para essa data.")
            else:
                raise
        except Exception as e:
            logger.error(f"[Santo do Dia] Erro inesperado ao gerar dinamicamente para {data_alvo}: {e}")
            raise HTTPException(status_code=500, detail=f"Erro ao obter santo do dia: {str(e)}")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Santo do Dia API] Erro ao consultar: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao obter santo do dia: {str(e)}")
    finally:
        if conn:
            conn.close()

