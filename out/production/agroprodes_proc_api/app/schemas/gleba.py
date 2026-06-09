from pydantic import BaseModel, Field, ConfigDict

class RequisicaoGleba(BaseModel):
    id_produtor: int = Field(..., description="ID identificador único do produtor rural")

    # Passamos a validação de formato espacial WKT para o campo de geometria correto
    geometria: str = Field(
        ...,
        pattern=r"^(?i)(POLYGON|MULTIPOLYGON)\s*\(\s*\(.*\)\s*\)$",
        description="Geometria da gleba em formato de texto WKT (Well-Known Text) utilizando EPSG:4326"
    )

    cultura_declarada: str = Field(..., description="Nome da cultura (ex: Soja, Milho)")

    # Retornamos o padrão correto de data (YYYY-MM-DD) para este campo
    data_estimada_plantio: str = Field(
        ...,
        pattern=r"^\d{4}-\d{2}-\d{2}$",
        description="Data estimada para o início do plantio no formato YYYY-MM-DD"
    )

    # Configurações para integração com esquemas externos/customizados e Swagger
    model_config = ConfigDict(
        title="Requisição de Gleba Agro",
        populate_by_name=True,
        json_schema_extra={
            "documentacao_sistema": "Mapeamento e conformidade técnica de polígonos via WKT para o AgroProdes.",
            "examples": [
                {
                    "id_produtor": 42,
                    "geometria": "POLYGON ((-44.41621163950453 -9.968400492342242, -44.4124856656675 -9.970974219395787, -44.413413947835 -9.978122110772, -44.4160249853 -9.984685866199001, -44.41621163950453 -9.968400492342242))",
                    "cultura_declarada": "Soja",
                    "data_estimada_plantio": "2026-10-15"
                }
            ]
        }
    )
