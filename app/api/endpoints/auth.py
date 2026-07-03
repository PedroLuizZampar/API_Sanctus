import logging
import random
import string
from fastapi import APIRouter, HTTPException, Depends
from app.models import schemas
from app.core import security
from app.db import connection, queries

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

@router.post("/register")
async def register(req: schemas.RegisterRequest, conn=Depends(connection.get_db_connection)):
    email = req.email.strip().lower()
    nome = req.nome.strip()
    password = req.password

    if not email or not nome or not password:
        raise HTTPException(status_code=400, detail="Nome, e-mail e senha são obrigatórios.")

    # Verificar se e-mail já existe
    existing_user = queries.obter_usuario_por_email(conn, email)
    if existing_user:
        raise HTTPException(status_code=400, detail="E-mail já cadastrado.")

    # Hashing da senha
    p_hash = security.hash_password(password)

    # Inserir usuário
    user = queries.criar_usuario(conn, nome, email, p_hash)
    if not user:
        raise HTTPException(status_code=500, detail="Erro interno ao registrar usuário.")

    user_id, u_nome, u_email, u_avatar = user[0], user[1], user[2], user[3]
    token = security.create_access_token(user_id, u_email)

    return {
        "user": {
            "id": str(user_id),
            "nome": u_nome,
            "email": u_email,
            "avatar_url": u_avatar
        },
        "token": token
    }

@router.post("/login")
async def login(req: schemas.LoginRequest, conn=Depends(connection.get_db_connection)):
    email = req.email.strip().lower()
    password = req.password

    if not email or not password:
        raise HTTPException(status_code=400, detail="E-mail e senha são obrigatórios.")

    user = queries.obter_usuario_por_email(conn, email)

    if not user or not security.verify_password(password, user[3]):
        raise HTTPException(status_code=400, detail="Credenciais inválidas.")

    user_id, u_nome, u_email, _, u_avatar = user[0], user[1], user[2], user[3], user[4]
    token = security.create_access_token(user_id, u_email)

    return {
        "user": {
            "id": str(user_id),
            "nome": u_nome,
            "email": u_email,
            "avatar_url": u_avatar
        },
        "token": token
    }

@router.post("/forgot-password")
async def forgot_password(req: schemas.ForgotPasswordRequest, conn=Depends(connection.get_db_connection)):
    email = req.email.strip().lower()
    if not email:
        raise HTTPException(status_code=400, detail="E-mail é obrigatório.")
        
    user = queries.obter_usuario_por_email(conn, email)
    if not user:
        logger.info(f"[Forgot Password] Solicitação para e-mail inexistente: {email}")
        raise HTTPException(status_code=404, detail="E-mail não cadastrado.")
        
    caracteres = string.ascii_letters + string.digits
    nova_senha = "".join(random.choice(caracteres) for _ in range(6))
    
    p_hash = security.hash_password(nova_senha)
    
    # Atualiza a senha e invalida token de redefinição
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE users SET password_hash = %s, reset_token = NULL, reset_token_expires = NULL, updated_at = CURRENT_TIMESTAMP WHERE email = %s",
            (p_hash, email)
        )
    
    logger.info("*" * 60)
    logger.info(f"[EMAIL SIMULADO] Enviando e-mail para: {email}")
    logger.info(f"Sua nova senha temporária de acesso é: {nova_senha}")
    logger.info("*" * 60)
    
    return {
        "detail": "Uma nova senha temporária foi enviada para o seu e-mail.",
        "temp_password": nova_senha
    }

@router.post("/reset-password")
async def reset_password(req: schemas.ResetPasswordRequest, conn=Depends(connection.get_db_connection)):
    email = req.email.strip().lower()
    token = req.token.strip()
    new_password = req.new_password
    
    if not email or not token or not new_password:
        raise HTTPException(status_code=400, detail="E-mail, código e nova senha são obrigatórios.")
        
    if len(new_password) < 6:
        raise HTTPException(status_code=400, detail="A nova senha deve possuir no mínimo 6 caracteres.")
        
    row = queries.obter_usuario_por_reset_token(conn, email, token)
    if not row:
        raise HTTPException(status_code=400, detail="E-mail ou código inválido.")
        
    import time
    db_expires = row[1]
    now = int(time.time())
    
    if db_expires and now > db_expires:
        raise HTTPException(status_code=400, detail="Código de recuperação expirado.")
        
    new_hash = security.hash_password(new_password)
    
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE users SET password_hash = %s, reset_token = NULL, reset_token_expires = NULL, updated_at = CURRENT_TIMESTAMP WHERE email = %s",
            (new_hash, email)
        )
        
    return {"detail": "Senha redefinida com sucesso."}
