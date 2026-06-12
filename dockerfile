FROM python:3.11-slim

# 1. Instalar dependências nativas do sistema operacional (C++/Geoespaciais)
RUN apt-get update && apt-get install -y --no-install-recommends \
    binutils \
    libgdal-dev \
    gdal-bin \
    libexpat1 \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# 2. Configurar variáveis de ambiente cruciais para compilação do GDAL
ENV CPLUS_INCLUDE_PATH=/usr/include/gdal
ENV C_INCLUDE_PATH=/usr/include/gdal
# Informa ao pip a versão exata do GDAL do sistema para evitar falhas de linkagem
RUN export GDAL_VERSION=$(gdal-config --version)

WORKDIR /app

# 3. Copiar requirements e garantir ferramentas de build atualizadas
COPY requirements.txt .

# Atualiza pip, setuptools e wheel antes de instalar as dependências
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir --force-reinstall -r requirements.txt

COPY . .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
