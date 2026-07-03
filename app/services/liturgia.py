import httpx
import logging

logger = logging.getLogger(__name__)

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
