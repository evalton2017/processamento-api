# app/services/analista/raster_service.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException, status
from datetime import date
import httpx
from datetime import datetime
from typing import AsyncGenerator

from app.models.gleba_model import MetadadosRaster


class RasterService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def obter_metadados_e_stream_url(self, id_raster: int) -> tuple[str, str]:
        """
        Consulta os novos campos raster_url e metadados no banco, validando a existência
        e gerando o nome de arquivo padronizado exigido pela auditoria do MAPA.
        """
        # Query limpa sem referências a 'payload', usando a classe do ORM declarativo
        query = (
            select(
                MetadadosRaster.raster_url,
                MetadadosRaster.id_gleba,
                MetadadosRaster.data_captura
            )
            .where(MetadadosRaster.id_raster == id_raster)
        )

        execucao = await self.db.execute(query)
        registro = execucao.first()

        if not registro or not registro.raster_url:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Os metadados ou a URL do arquivo raster {id_raster} não foram localizados."
            )

        # Tratamento seguro da data para formatação do nome do arquivo final
        data_imagem = registro.data_captura
        data_formatada = data_imagem.strftime("%Y-%m-%d") if isinstance(data_imagem, (date, datetime)) else "data-indisponivel"
        nome_arquivo_saida = f"MAPA_VGM_CONTRATO_GLEBA_{registro.id_gleba}_{data_formatada}.tif"

        return registro.raster_url, nome_arquivo_saida

    async def stream_geotiff_remoto(self, url: str) -> AsyncGenerator[bytes, None]:
        """
        Garante eficiência de infraestrutura: faz o download em chunks da URL de armazenamento
        e repassa diretamente para o cliente HTTP sem estourar a memória RAM do servidor.
        """
        timeout = httpx.Timeout(60.0, connect=10.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream("GET", url) as response:
                if response.status_code != 200:
                    raise HTTPException(
                        status_code=status.HTTP_502_BAD_GATEWAY,
                        detail="Falha ao recuperar o arquivo GeoTIFF do servidor de armazenamento externo."
                    )

                # Lê blocos de 128KB por vez e faz o yield para o streaming
                async for chunk in response.aiter_bytes(chunk_size=131072):
                    yield chunk
