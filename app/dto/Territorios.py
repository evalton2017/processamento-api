from pydantic import BaseModel, ConfigDict, Field


class RequisicaoTerritorio(BaseModel):
    hash_transacao: str | None = Field(
        None,
        max_length=100,
        description="Hash identificador único da transação na blockchain ou sistema de origem",
    )

    numero_car: str = Field(
        ...,
        max_length=100,
        description="Número do Cadastro Ambiental Rural (CAR) associado ao território",
    )

    nome_propriedade: str = Field(
        ..., max_length=255, description="Nome oficial da propriedade rural"
    )

    # Validação WKT flexível para aceitar os tipos geométricos mais comuns (POINT, POLYGON, MULTIPOLYGON, etc.)
    geometry: str = Field(
        ...,
        pattern=r"^(?i)(POINT|LINESTRING|POLYGON|MULTIPOINT|MULTILINESTRING|MULTIPOLYGON|GEOMETRYCOLLECTION)\s*\(.*\)$",
        description="Geometria do território em formato WKT (Well-Known Text) utilizando EPSG:4674",
    )

    area_hectares: float = Field(
        ..., gt=0, description="Área total calculada da propriedade em hectares"
    )

    # Validação de data no formato ISO completo (YYYY-MM-DD THH:MM:SS) ou simples (YYYY-MM-DD)
    data_criacao: str = Field(
        ...,
        pattern=r"^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}:\d{2})?$",
        description="Data de criação original do registro no formato YYYY-MM-DD ou YYYY-MM-DDTHH:MM:SS",
    )

    cultura_declarada: str = Field(
        ..., max_length=255, description="Nome da cultura declarada (ex: Café)"
    )

    usuario: str = Field(
        ...,
        max_length=50,
        description="Nome de usuário ou identificador do responsável pelo cadastro",
    )

    model_config = ConfigDict(
        title="Requisição de Território Agro",
        populate_by_name=True,
        json_schema_extra={
            "documentacao_sistema": "Mapeamento, validação cadastral e conformidade técnica de territórios via WKT para o AgroProdes.",
            "examples": [
                {
                    "numero_car": "BR-MG-3106200-1234567890ABCDEF12345",
                    "nome_propriedade": "Fazenda Boa Vista",
                    "geometry": "POLYGON ((-44.41621163950453 -9.968400492342242, -44.4124856656675 -9.970974219395787, -44.413413947835 -9.978122110772, -44.4160249853 -9.984685866199001, -44.41621163950453 -9.968400492342242))",
                    "area_hectares": 150.75,
                    "data_criacao": "2026-06-10T10:30:00",
                    "cultura_declarada": "Café"
                }
            ],
        },
    )

