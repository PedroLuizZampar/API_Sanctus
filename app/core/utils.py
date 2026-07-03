from datetime import datetime
from zoneinfo import ZoneInfo

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
