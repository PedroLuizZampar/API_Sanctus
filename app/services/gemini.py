from google import genai
from app.core import config

gemini_client = None
GEMINI_MODEL = "gemini-2.5-flash"

def get_gemini_client() -> genai.Client:
    """Inicializa o cliente Gemini apenas quando necessário."""
    global gemini_client
    if gemini_client is None:
        if not config.GEMINI_API_KEY:
            raise RuntimeError("Variável GEMINI_API_KEY não configurada.")
        gemini_client = genai.Client(api_key=config.GEMINI_API_KEY)
    return gemini_client

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
