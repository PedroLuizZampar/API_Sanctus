import os
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.db import connection
from app.api.endpoints import auth, user, sync, chat, daily

# =============================================================================
# Configuração de Logging
# =============================================================================
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# =============================================================================
# FastAPI App
# =============================================================================
app = FastAPI(
    title="API Católica",
    description="API modularizada para servir meditações, curiosidades, bíblia e sincronização.",
    version="1.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "PUT", "OPTIONS"],
    allow_headers=["*"],
)

os.makedirs("static/avatars", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

# =============================================================================
# Registro de Rotas (Roteadores)
# =============================================================================
app.include_router(auth.router)
app.include_router(user.router)
app.include_router(sync.router)
app.include_router(chat.router)
app.include_router(daily.router)

# =============================================================================
# Eventos de Ciclo de Vida (Startup e Shutdown)
# =============================================================================
@app.on_event("startup")
def startup_event():
    """Garante a inicialização do Connection Pool e das Tabelas DDL."""
    logger.info("Iniciando API Católica e configurando conexões...")
    try:
        connection.init_db_pool()
        # Obtém uma conexão temporária do pool para garantir as tabelas
        conn = connection.db_pool.getconn()
        try:
            connection.garantir_tabelas(conn)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            connection.db_pool.putconn(conn)
    except Exception as e:
        logger.error(f"Erro crítico ao inicializar o banco de dados no startup: {e}")

@app.on_event("shutdown")
def shutdown_event():
    """Fecha todas as conexões do pool no encerramento da API."""
    logger.info("Encerrando API Católica...")
    connection.close_db_pool()
