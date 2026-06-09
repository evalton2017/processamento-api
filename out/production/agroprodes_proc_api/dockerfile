# Estágio 1: Construção (Build)
FROM python:3.11-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
build-essential \
        && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# Instala as dependências isoladas em uma pasta local
RUN pip install --no-cache-dir --user -r requirements.txt


# Estágio 2: Execução (Runtime) - Garante uma imagem final leve e segura
FROM python:3.11-slim AS runner

WORKDIR /app

# Copia as dependências instaladas do estágio anterior
COPY --from=builder /root/.local /root/.local
COPY . .

# Garante que o Python encontre as dependências copiadas
ENV PATH=/root/.local/bin:$PATH
ENV PYTHONUNBUFFERED=1

# Expõe a porta interna da aplicação
EXPOSE 8000

# Executa a API usando Uvicorn (substitua por Gunicorn se usar Flask)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
