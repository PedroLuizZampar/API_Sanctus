import os
import logging
from fastapi import APIRouter, HTTPException, Depends, File, UploadFile
from app.models import schemas
from app.core import security
from app.db import connection, queries

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/user", tags=["user"])

@router.post("/upload-avatar")
async def upload_avatar(
    file: UploadFile = File(...),
    user_id: str = Depends(security.get_current_user_id),
    conn=Depends(connection.get_db_connection)
):
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Formato de arquivo inválido. Apenas imagens são permitidas.")
    
    os.makedirs(os.path.join("static", "avatars"), exist_ok=True)
    ext = "jpg"
    filename = f"{user_id}.{ext}"
    filepath = os.path.join("static", "avatars", filename)
    
    try:
        content = await file.read()
        with open(filepath, "wb") as f:
            f.write(content)
            
        avatar_url = f"/static/avatars/{filename}"
        queries.atualizar_avatar_usuario(conn, user_id, avatar_url)
        return {"avatar_url": avatar_url}
    except Exception as e:
        logger.error(f"[User Upload Avatar] Erro: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao processar upload do avatar: {str(e)}")

@router.put("/update-email")
async def update_email(
    req: schemas.UpdateEmailRequest,
    user_id: str = Depends(security.get_current_user_id),
    conn=Depends(connection.get_db_connection)
):
    new_email = req.new_email.strip().lower()
    if not new_email:
        raise HTTPException(status_code=400, detail="E-mail inválido.")
        
    with conn.cursor() as cur:
        # Verificar se já existe esse e-mail em outro usuário
        cur.execute("SELECT id FROM users WHERE email = %s AND id <> %s", (new_email, user_id))
        if cur.fetchone():
            raise HTTPException(status_code=400, detail="E-mail já está em uso por outro usuário.")
            
    queries.atualizar_email_usuario(conn, user_id, new_email)
    return {"detail": "E-mail atualizado com sucesso."}

@router.put("/update-password")
async def update_password(
    req: schemas.UpdatePasswordRequest,
    user_id: str = Depends(security.get_current_user_id),
    conn=Depends(connection.get_db_connection)
):
    current_password = req.current_password
    new_password = req.new_password
    
    if not current_password or not new_password:
        raise HTTPException(status_code=400, detail="Senhas atual e nova são obrigatórias.")
        
    if len(new_password) < 6:
        raise HTTPException(status_code=400, detail="A nova senha deve ter no mínimo 6 caracteres.")
        
    user = queries.obter_usuario_por_id(conn, user_id)
    if not user or not security.verify_password(current_password, user[3]):
        raise HTTPException(status_code=400, detail="Senha atual incorreta.")
        
    new_hash = security.hash_password(new_password)
    queries.atualizar_senha_usuario(conn, user_id, new_hash)
    return {"detail": "Senha atualizada com sucesso."}
