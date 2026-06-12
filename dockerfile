FROM python:3.11-slim

# 1. Instalar dependências nativas e ferramentas de compilação
RUN apt-get update && apt-get install -y --no-install-recommends \
    binutils \
    libgdal-dev \
    gdal-bin \
    libexpat1 \
    gcc \
    g++ \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

# 2. Configurar caminhos do GDAL exigidos pelas bibliotecas Python
ENV CPLUS_INCLUDE_PATH=/usr/include/gdal
ENV C_INCLUDE_PATH=/usr/include/gdal

WORKDIR /app

# 3. Copiar e preparar o ambiente de pacotes do Python
COPY requirements.txt .

# 4. Atualizar ferramentas de build em uma camada separada
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

# 5. Instalar o GDAL explicitamente antes do restante dos pacotes
RUN pip install --no-cache-dir GDAL==$(gdal-config --version)

# 6. Instalar os demais pacotes do projeto
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
