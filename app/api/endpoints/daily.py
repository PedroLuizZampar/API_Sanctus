import os
import random
import json
import logging
import asyncio
from fastapi import APIRouter, Depends, HTTPException, Query
from app.core import prompts, utils
from app.db import connection, queries
from app.services import gemini, liturgia, scraper

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["daily"])

@router.post("/gerar-conteudo")
async def gerar_conteudo(conn=Depends(connection.get_db_connection)):
    data_hoje = utils.obter_data_hoje()
    logger.info(f"[Gerar Conteúdo] Iniciando para a data: {data_hoje}")

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
        logger.info("[Gerar Conteúdo] Todos os conteúdos já existem para hoje. Pulando.")
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

        async def gerar_meditacao_task():
            nonlocal texto_meditacao
            evangelho = await liturgia.obter_evangelho_do_dia(data_hoje)
            data_extenso = utils.obter_data_por_extenso()

            prompt = prompts.PROMPT_EVANGELHO
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

            texto_meditacao = await gemini.chamar_gemini(prompt)

        tarefas.append(gerar_meditacao_task())

    if not tem_curiosidade:
        logger.info("[Gerar Conteúdo] Preparando geração da curiosidade...")

        async def gerar_curiosidade_task():
            nonlocal texto_curiosidade
            # Subir 4 níveis a partir de app/api/endpoints/daily.py para chegar na raiz da API
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
            temas_file = os.path.join(base_dir, "Temas_Curiosidades.txt")
            tema_escolhido = "um assunto católico aleatório e fascinante"

            try:
                if os.path.exists(temas_file):
                    with open(temas_file, "r", encoding="utf-8") as f:
                        temas = [linha.strip() for linha in f if linha.strip()]
                    if temas:
                        tema_escolhido = random.choice(temas)
                        logger.info(f"[Gerar Conteúdo] Tema de curiosidade escolhido: '{tema_escolhido}'")
                    else:
                        logger.warning("[Gerar Conteúdo] Arquivo de temas de curiosidades está vazio. Usando fallback.")
                else:
                    logger.warning(f"[Gerar Conteúdo] Arquivo {temas_file} não encontrado. Usando fallback.")
            except Exception as e:
                logger.error(f"[Gerar Conteúdo] Erro ao ler arquivo de temas: {e}. Usando fallback.")

            prompt_formatado = prompts.PROMPT_CURIOSIDADES.format(tema=tema_escolhido)
            texto_curiosidade = await gemini.chamar_gemini(prompt_formatado)

        tarefas.append(gerar_curiosidade_task())

    if not tem_santo:
        logger.info("[Gerar Conteúdo] Preparando scrape do Santo do Dia...")

        async def gerar_santo_task():
            nonlocal santo_data
            santo_data = await scraper.extrair_santo_do_dia_por_data(data_hoje)

        tarefas.append(gerar_santo_task())

    if not tem_liturgia:
        logger.info("[Gerar Conteúdo] Preparando scrape da Liturgia Diária...")

        async def gerar_liturgia_task():
            nonlocal liturgia_data
            liturgia_data = await scraper.extrair_liturgia_diaria_por_data(data_hoje)

        tarefas.append(gerar_liturgia_task())

    # 3. Executar tarefas em paralelo
    await asyncio.gather(*tarefas)
    logger.info("[Gerar Conteúdo] Conteúdos processados com sucesso.")

    # 4. Salvar no Neon DB
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

@router.get("/meditacao")
async def obter_meditacao(date: str = Query(default=None, description="Data no formato YYYY-MM-DD"), conn=Depends(connection.get_db_connection)):
    data_alvo = date or utils.obter_data_hoje()
    conteudo = queries.obter_meditacao_por_data(conn, data_alvo)
    if conteudo:
        return {"markdown": conteudo, "date": data_alvo, "isLatestFallback": False}

    raise HTTPException(status_code=404, detail="Nenhuma meditação disponível para a data especificada.")

@router.get("/curiosidades")
async def obter_curiosidades(date: str = Query(default=None, description="Data no formato YYYY-MM-DD"), conn=Depends(connection.get_db_connection)):
    data_alvo = date or utils.obter_data_hoje()
    conteudo = queries.obter_curiosidade_por_data(conn, data_alvo)
    if conteudo:
        return {"markdown": conteudo, "date": data_alvo, "isLatestFallback": False}

    raise HTTPException(status_code=404, detail="Nenhuma curiosidade disponível para a data especificada.")

@router.get("/liturgia")
async def obter_liturgia_diaria(date: str = Query(default=None, description="Data no formato YYYY-MM-DD"), conn=Depends(connection.get_db_connection)):
    data_alvo = date or utils.obter_data_hoje()
    conteudo = queries.obter_liturgia_por_data(conn, data_alvo)
    if conteudo:
        return json.loads(conteudo)

    logger.warning(f"[Liturgia Diária] Nenhuma liturgia encontrada no Neon para a data {data_alvo}. Gerando dinamicamente.")
    try:
        liturgia_gerada = await scraper.extrair_liturgia_diaria_por_data(data_alvo)
        queries.salvar_liturgia(conn, data_alvo, json.dumps(liturgia_gerada, ensure_ascii=False))
        return liturgia_gerada
    except Exception as scrap_err:
        logger.error(f"[Liturgia Diária] Falha ao obter dinamicamente para {data_alvo}: {scrap_err}.")
        raise HTTPException(status_code=404, detail="Liturgia diária não disponível para a data especificada.")

@router.get("/santo-do-dia")
async def obter_santo_do_dia(date: str = Query(default=None, description="Data no formato YYYY-MM-DD"), conn=Depends(connection.get_db_connection)):
    data_alvo = date or utils.obter_data_hoje()
    data_hoje = utils.obter_data_hoje()
    
    conteudo = queries.obter_santo_por_data(conn, data_alvo)
    if conteudo:
        santo_json = json.loads(conteudo)
        santo_json["isLatestFallback"] = False
        santo_json["date"] = data_alvo
        return santo_json

    logger.warning(f"[Santo do Dia] Nenhum santo encontrado no Neon para a data {data_alvo}. Gerando dinamicamente.")
    try:
        santo_gerado = await scraper.extrair_santo_do_dia_por_data(data_alvo, fallback_home=(data_alvo == data_hoje))
        queries.salvar_santo(conn, data_alvo, json.dumps(santo_gerado, ensure_ascii=False))
        santo_gerado["isLatestFallback"] = False
        santo_gerado["date"] = data_alvo
        return santo_gerado
    except HTTPException as scrap_err:
        if scrap_err.status_code == 404:
            logger.warning(f"[Santo do Dia] Registro inexistente para {data_alvo}. Verificando hoje real ({data_hoje}).")
            tem_hoje = queries.obter_santo_por_data(conn, data_hoje)
            if not tem_hoje:
                try:
                    santo_hoje = await scraper.extrair_santo_do_dia_por_data(data_hoje, fallback_home=True)
                    queries.salvar_santo(conn, data_hoje, json.dumps(santo_hoje, ensure_ascii=False))
                    logger.info(f"[Santo do Dia] Criado registro de hoje real ({data_hoje}) na checagem.")
                except Exception as e_hoje:
                    logger.error(f"[Santo do Dia] Falha ao criar hoje real: {e_hoje}")
            
            raise HTTPException(status_code=404, detail="Não existem registros do Santo do Dia para essa data.")
        else:
            raise
    except Exception as e:
        logger.error(f"[Santo do Dia] Erro inesperado ao gerar dinamicamente para {data_alvo}: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao obter santo do dia: {str(e)}")
