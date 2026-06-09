FROM python:3.11-slim AS builder
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Cria um ambiente virtual isolado
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# Estágio 2: Execução (Runtime)
FROM python:3.11-slim AS runner
WORKDIR /app
# Copia o ambiente virtual completo com todas as dependências e binários
COPY --from=builder /opt/venv /opt/venv
COPY . .

# Ativa o ambiente virtual no PATH para o runner
ENV PATH="/opt/venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
