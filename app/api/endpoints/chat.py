import logging
import httpx
from fastapi import APIRouter, HTTPException, Header
from app.core import config

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/chat", tags=["chat"])

@router.post("")
async def proxy_chat(
    payload: dict,
    x_sanctus_token: str = Header(default=None, alias="x-sanctus-token")
):
    """
    Proxy seguro para a API do Magisterium AI.
    Valida o token compartilhado 'x-sanctus-token' antes de fazer o redirecionamento.
    """
    # 1. Validar se o token do App foi configurado no servidor
    if config.SANCTUS_APP_TOKEN and x_sanctus_token != config.SANCTUS_APP_TOKEN:
        logger.warning(f"[Proxy Chat] Acesso não autorizado. Header: {x_sanctus_token}")
        raise HTTPException(
            status_code=401,
            detail="Acesso não autorizado: Token inválido ou ausente."
        )

    # 2. Validar se a chave do Magisterium AI está configurada no servidor
    if not config.MAGISTERIUM_API_KEY:
        logger.error("[Proxy Chat] Chave MAGISTERIUM_API_KEY não configurada no servidor.")
        raise HTTPException(
            status_code=500,
            detail="Chave de API do Magisterium AI não configurada no servidor."
        )

    url = "https://www.magisterium.com/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {config.MAGISTERIUM_API_KEY}",
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
