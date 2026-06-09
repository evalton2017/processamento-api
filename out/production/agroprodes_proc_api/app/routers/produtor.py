import asyncio
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.session import get_db, get_ledger_db
from app.database.models_principal import GlebaModel
from app.database.models_ledger import ConsentimentoLgpdLedgerModel
from app.schemas.gleba import RequisicaoGleba

router = APIRouter(prefix="/api/v1/produtor", tags=["Produtor Rural"])

@router.post("/cadastrar-gleba", status_code=status.HTTP_201_CREATED)
async def cadastrar_gleba_vmg(
        dados: RequisicaoGleba,
        db_principal: AsyncSession = Depends(get_db),
        db_ledger: AsyncSession = Depends(get_ledger_db)
):
    try:
        # O 'begin()' abre a transação. Se o bloco terminar sem erros, ele faz o COMMIT automático.
        # Se ocorrer qualquer exceção interna, ele faz o ROLLBACK automático de ambas as bases.
        async with db_principal.begin(), db_ledger.begin():

            # 1. Persistência no banco principal (agroprods)
            nova_gleba = GlebaModel(
                id_produtor=dados.id_produtor,
                geometria=dados.geometria,
                area_hectares=150.50
            )
            db_principal.add(nova_gleba)

            # O flush sincroniza com o banco e gera o id_gleba sem fechar a transação
            await db_principal.flush()

            # 2. Persistência no banco de auditoria (ledger)
            novo_consentimento = ConsentimentoLgpdLedgerModel(
                id_produtor=dados.id_produtor,
                autorizado_cruzamento_car=True,
                ip_origem="192.168.1.50",
                dispositivo_token="token_exemplo_vmg_2026"
            )
            db_ledger.add(novo_consentimento)

            # Opcional: Garante que os dados do ledger cheguem ao banco antes de sair do bloco
            await db_ledger.flush()

        # Fora do bloco 'async with', ambas as bases já realizaram o commit com sucesso.
        return {
            "status": "SUCESSO",
            "mensagem": "Dados persistidos com sucesso nos esquemas correspondentes.",
            "id_gleba_gerado": nova_gleba.id_gleba
        }

    except Exception as e:
        # Não é necessário chamar rollback manual aqui, o 'async with db.begin()' já tratou isso.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro na transação distribuída: {str(e)}"
        )
