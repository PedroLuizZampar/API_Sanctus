# API Sanctus

API em Python construída com **FastAPI** para gerar e servir meditações diárias do Evangelho e curiosidades católicas. Ela se conecta ao **Google Gemini** para gerar o conteúdo, salva em um banco de dados **Neon PostgreSQL** e é projetada para ser hospedada no **Render**.

---

## 🚀 Como Iniciar Localmente

### 1. Requisitos
Certifique-se de ter o Python 3.10+ instalado.

### 2. Instalar Dependências
```bash
pip install -r requirements.txt
```

### 3. Configurar Variáveis de Ambiente
Crie um arquivo `.env` a partir do `.env.example`:
```bash
cp .env.example .env
```
Abra o arquivo `.env` e preencha com as suas credenciais:
- `GEMINI_API_KEY`: Sua chave de acesso à API do Google Gemini.
- `NEON_DATABASE_URL`: Connection string do seu banco de dados PostgreSQL no Neon.

### 4. Executar a API
Para rodar em desenvolvimento:
```bash
uvicorn main:app --reload
```
A API estará acessível em `http://127.0.0.1:8000`.

---

## 🔗 Rotas Disponíveis

- **`POST /api/v1/gerar-conteudo`**: Rota automatizada (chamada via Cron externo diariamente) para gerar a meditação do Evangelho do dia e a curiosidade católica, salvando-as no banco.
- **`GET /api/v1/meditacao?date=YYYY-MM-DD`**: Busca a meditação correspondente à data informada. Caso não encontre, retorna a mais recente como fallback.
- **`GET /api/v1/curiosidades?date=YYYY-MM-DD`**: Busca a curiosidade correspondente à data informada. Caso não encontre, retorna a mais recente como fallback.

---

## 🗄️ Schema do Banco de Dados
A API cria automaticamente as tabelas necessárias na inicialização:

```sql
CREATE TABLE IF NOT EXISTS meditacoes_evangelho (
    id SERIAL PRIMARY KEY,
    conteudo TEXT NOT NULL,
    data DATE UNIQUE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS curiosidades_catolicas (
    id SERIAL PRIMARY KEY,
    conteudo TEXT NOT NULL,
    data DATE UNIQUE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
```

---

## ☁️ Deploy no Render

1. Crie um novo repositório Git com os arquivos da API.
2. Crie um **Web Service** no Render e conecte o repositório.
3. Configure os comandos:
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`
4. Adicione as variáveis de ambiente `GEMINI_API_KEY` e `NEON_DATABASE_URL`.
5. Crie um Cron Job em [cron-job.org](https://cron-job.org) apontando para o endpoint `POST /api/v1/gerar-conteudo` para rodar diariamente (por exemplo, às 07:00 Horário de Brasília / 10:00 UTC).
