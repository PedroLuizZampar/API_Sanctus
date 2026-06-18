import os
import asyncio
import time
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
import psycopg2
from psycopg2 import sql
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from google import genai

# =============================================================================
# Configuração de Logging
# =============================================================================
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# =============================================================================
# Variáveis de Ambiente
# =============================================================================
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
NEON_DATABASE_URL = os.environ.get("NEON_DATABASE_URL", "")

# =============================================================================
# Cliente do Gemini (biblioteca oficial google-genai)
# =============================================================================
gemini_client = genai.Client(api_key=GEMINI_API_KEY)
GEMINI_MODEL = "gemini-2.5-flash"

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
  Atue como um Professor de História da Igreja e Catequista dinâmico. Quero que você crie um texto fascinante, rico em conteúdo e altamente visual sobre um assunto curioso, artístico, histórico ou teológico da fé católica (Ex: arquitetura, relíquias, catacumbas, sacramentais, vestes litúrgicas, tradições esquecidas).

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

## Escolha um assunto católico aleatório e fascinante e gere o texto seguindo o modelo acima.
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
    if not GEMINI_API_KEY:
        raise RuntimeError("Variável GEMINI_API_KEY não configurada.")

    response = gemini_client.models.generate_content(
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
    """
    Gera a meditação do Evangelho e a curiosidade católica do dia.
    Chamado diariamente pelo cron-job.org.
    Sem parâmetros, sem autenticação.
    """
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

        if tem_meditacao and tem_curiosidade:
            logger.info("[Gerar Conteúdo] Meditação e curiosidade já existem para hoje. Pulando.")
            return {
                "message": "Registros já atualizados para hoje.",
                "date": data_hoje,
                "actions": {"meditacao": "skipped", "curiosidade": "skipped"},
            }

        # 2. Preparar as tarefas de geração em paralelo
        tarefas = []
        texto_meditacao = ""
        texto_curiosidade = ""

        if not tem_meditacao:
            logger.info("[Gerar Conteúdo] Preparando geração da meditação...")

            async def gerar_meditacao():
                nonlocal texto_meditacao
                # Buscar evangelho do dia
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
                texto_curiosidade = await chamar_gemini(PROMPT_CURIOSIDADES)

            tarefas.append(gerar_curiosidade())

        # 3. Executar chamadas ao Gemini em paralelo
        await asyncio.gather(*tarefas)
        logger.info("[Gerar Conteúdo] Textos gerados com sucesso via Gemini.")

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

        conn.commit()
        logger.info("[Gerar Conteúdo] Registros salvos com sucesso no Neon DB.")

        return {
            "message": "Geração e salvamento concluídos com sucesso.",
            "date": data_hoje,
            "actions": {
                "meditacao": "generated" if not tem_meditacao else "skipped",
                "curiosidade": "generated" if not tem_curiosidade else "skipped",
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
    """Retorna a meditação do Evangelho para a data informada (ou a mais recente como fallback)."""
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

            # 2. Fallback: buscar a mais recente
            cur.execute(
                "SELECT conteudo, data FROM meditacoes_evangelho ORDER BY data DESC LIMIT 1"
            )
            row = cur.fetchone()

            if row:
                return {"markdown": row[0], "date": str(row[1]), "isLatestFallback": True}

        raise HTTPException(status_code=404, detail="Nenhuma meditação disponível no momento.")

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
    """Retorna a curiosidade católica para a data informada (ou a mais recente como fallback)."""
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

            # 2. Fallback: buscar a mais recente
            cur.execute(
                "SELECT conteudo, data FROM curiosidades_catolicas ORDER BY data DESC LIMIT 1"
            )
            row = cur.fetchone()

            if row:
                return {"markdown": row[0], "date": str(row[1]), "isLatestFallback": True}

        raise HTTPException(status_code=404, detail="Nenhuma curiosidade disponível no momento.")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[API Curiosidades] Erro: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao consultar curiosidades: {str(e)}")
    finally:
        if conn:
            conn.close()
