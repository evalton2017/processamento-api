from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from app.services.produtividade_service import estimar_e_validar_produtividade

router = APIRouter(prefix="/api/v1/validacao", tags=["Quantificação e Comercialização"])

class RequisicaoComercializacao(BaseModel):
    id_gleba: int
    cultura: str = Field(..., example="SOJA")
    sacas_para_comercializar: float = Field(..., gt=0, description="Quantidade total de sacas que o produtor deseja vender")
    area_hectares: float = Field(..., gt=0, description="Área medida total da gleba em hectares")

@router.post("/validar-volume-venda", status_code=status.HTTP_200_OK)
async def validar_volume_comercializacao(dados: RequisicaoComercializacao):
    """
    Executa a verificação automatizada se a produtividade da área delimitada no período
    é condizente com a quantidade de sacas que o produtor deseja comercializar.
    """
    try:
        # Mocks de dados que seriam recuperados via banco SGBDOR (PostGIS + Tabelas Climáticas)
        # vindos do histórico do satélite e da interpolação das estações INMET para o ciclo atual:
        ndvi_historico_ciclo = [0.15, 0.32, 0.65, 0.88, 0.82, 0.45] # Curva de crescimento
        chuva_acumulada_ciclo = 480.5 # mm medidos na gleba via IDW
        temperatura_media_ciclo = 24.8 # °C medidos na gleba via Spline

        # Executa o motor de inteligência e validação
        resultado = estimar_e_validar_produtividade(
            area_hectares=dados.area_hectares,
            sacas_desejadas_comercializar=dados.sacas_para_comercializar,
            valores_ndvi_ciclo=ndvi_historico_ciclo,
            total_chuva_ciclo_mm=chuva_acumulada_ciclo,
            media_temp_ciclo_c=temperatura_media_ciclo,
            cultura=dados.cultura
        )

        # Adiciona o ID de rastreabilidade do talhão no payload de retorno
        resultado["id_gleba"] = dados.id_gleba

        return resultado

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro interno ao processar a quantificação de produtividade: {str(e)}"
        )
