import os
from dotenv import load_dotenv

# Carrega variáveis de ambiente
load_dotenv()

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
NEON_DATABASE_URL = os.environ.get("NEON_DATABASE_URL", "")
MAGISTERIUM_API_KEY = os.environ.get("MAGISTERIUM_API_KEY", "")
SANCTUS_APP_TOKEN = os.environ.get("SANCTUS_APP_TOKEN", "")

# Configurações de Segurança e JWT
JWT_SECRET = os.environ.get("JWT_SECRET", "super_secret_sanctus_key_2026_xyz")
JWT_ALGORITHM = "HS256"
TOKEN_EXPIRE_MINUTES = 60 * 24 * 30  # 30 dias
