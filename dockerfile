FROM python:3.11-slim

# 1. Instalar dependências nativas do sistema operacional (C++/Geospeciais)
RUN apt-get update && apt-get install -y --no-install-recommends \
    binutils \
    libgdal-dev \
    gdal-bin \
    libexpat1 \
    && rm -rf /var/lib/apt/lists/*

# 2. Configurar variáveis de ambiente para o GDAL/Rasterio se necessário
ENV CPLUS_INCLUDE_PATH=/usr/include/gdal
ENV C_INCLUDE_PATH=/usr/include/gdal

WORKDIR /app

# 3. Copiar e instalar dependências do Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
