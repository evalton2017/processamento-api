# app/services/relatorio_service.py
import io
import os
from datetime import timedelta
from io import BytesIO
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
import pdfkit
from jinja2 import Environment, FileSystemLoader

import base64
from shapely.wkt import loads as load_wkt, loads
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

from app.dto.relatorio.relatorio_produtor import AtestadoDetalhadoResponse
from app.repository.relatorio_repository import RelatorioRepository


class RelatorioService:
    def __init__(self, db: AsyncSession):
        self.repository = RelatorioRepository(db)
        self.db = db

    async def gerar_relatorio_tela_atestado_por_gleba(self, id_gleba: int) -> Optional[AtestadoDetalhadoResponse]:
        async with self.db.begin():
            raw_data = await self.repository.obter_dados_atestado_por_gleba(id_gleba)
            if not raw_data:
                return None

            # Fallback caso a gleba exista mas não possua nenhum atestado emitido no ledger
            if not raw_data.get("id_atestado"):
                raw_data["status_validacao"] = "PENDENTE"
                raw_data["id_atestado"] = 0
                raw_data["hash_relatorio"] = "NÃO EMITIDO"

            conforme_ambiental = not any([
                raw_data.get("conflito_socioambiental"),
                raw_data.get("conflito_prodes"),
                raw_data.get("conflito_ibama_icmbio"),
                raw_data.get("conflito_comunidades")
            ])

            poligono = loads(raw_data.get("coordenadas_raw"))
            centroide = str(poligono.centroid)

            conforme_agricola = raw_data.get("status_conducao") == "CONDIZENTE"

            prod_declarada = float(raw_data.get("volume_comercializar_declarado") or 20.00)
            prod_estimada_ia = float(raw_data.get("produtividade_ia_sacas_ha") or raw_data.get("estimativa_produtividade_sacas") or 56.11)
            ref_regional = float(raw_data.get("referencia_regional_sacas_ha") or 76.00)

            # 2. Define a regra de negócio: Margem de tolerância admissível (ex: 20%)
            margem_tolerancia = 0.20
            diferenca_absoluta = abs(prod_declarada - prod_estimada_ia)

            # A produtividade estará CONFORME se a divergência entre o declarado e a IA
            # for menor ou igual à tolerância estipulada sobre a estimativa.
            if diferenca_absoluta <= (prod_estimada_ia * margem_tolerancia):
                produtividade_conforme_dinamica = True
            else:
                # Caso o produtor declare algo absurdamente fora do predito pela IA, vira divergente
                produtividade_conforme_dinamica = False
            # Validação extra de segurança: Se o declarado for maior que a referência histórica da região, bloqueia
            if prod_declarada > (ref_regional * 1.10):
                produtividade_conforme_dinamica = False


            return AtestadoDetalhadoResponse(
                cabecalho={
                    "nome_gleba": raw_data.get("nome_gleba"),
                    "cultura_principal": raw_data.get("cultura_principal") or "NÃO DECLARADA",
                    "safra": raw_data.get("safra") or "N/A",
                    "periodo_analisado": f"{raw_data.get('data_estimada_plantio')} a {raw_data.get('data_estimada_colheita')}" if raw_data.get('data_estimada_plantio') else "N/A",
                    "status_atestado": raw_data.get("status_validacao"),
                    "data_emissao_atestado": raw_data.get("data_emissao"),
                    "area_hectares": float(raw_data.get("area_hectares") or 0.0)
                },
                conformidade={
                    "ambiental_conforme": conforme_ambiental,
                    "agricola_conforme": conforme_agricola,
                    "boas_praticas_conforme": bool(raw_data.get("possui_certificado_bpa")),
                    "zarc_conforme": raw_data.get("validacao_zarc") == 'Aprovado',
                    "produtividade_conforme": produtividade_conforme_dinamica,
                    "produtividade_estimada_sacas": float(raw_data.get("produtividade_ia_sacas_ha") or 0.0),
                    "produtividade_declarada_sacas": float(raw_data.get("volume_comercializar_declarado") or 0.0)
                },
                informacoes_gerais={
                    "municipio_uf": raw_data.get("municipio_uf") or "Não Informado",
                    "codigo_car": raw_data.get("codigo_car") or "Não Informado",
                    "coordenadas_centroide": centroide,
                    "data_cadastro": raw_data.get("data_criacao")
                },
                linha_tempo_safra=[
                    {"fase": "Plantio", "data_evento": raw_data.get("data_estimada_plantio"), "tipo": "Estimado"} if raw_data.get("data_estimada_plantio") else {"fase": "Plantio", "data_evento": None, "tipo": "Pendente"},
                    {"fase": "Colheita", "data_evento": raw_data.get("data_estimada_colheita"), "tipo": "Estimado"} if raw_data.get("data_estimada_colheita") else {"fase": "Colheita", "data_evento": None, "tipo": "Pendente"}
                ],
                produtividade={
                    "declarado_sacas_ha": 60.0,
                    "estimado_ia_sacas_ha": float(raw_data.get("produtividade_ia_sacas_ha") or 0.0),
                    "referencia_regional_sacas_ha": 76.0
                },
                metadados_atestado={
                    "codigo_atestado": f"ATD-2025-{raw_data.get('id_atestado'):06d}" if raw_data.get('id_atestado') > 0 else "SEM EMISSÃO",
                    "orgao_emissor": "Secretaria de Inovação, Desenvolvimento Sustentável, Irrigação e Cooperativismo",
                    "metodo_validacao": "VMG - Portaria SDI/MAPA nº 739/2025",
                    "validade_inicio": raw_data.get("data_emissao"),
                    "validade_fim": raw_data.get("dt_fim"),
                    "hash_documento_blockchain": raw_data.get("hash_relatorio")
                }
            )

    def _gerar_imagem_mapa_base64(self, wkt_geometria: str, status_vmg: str) -> str:
        """
        Converte uma geometria espacial (WKT ou WKB Hex) em um gráfico vetorial
        com imagem de fundo de satélite real (ArcGIS MapServer) via Contextily.
        """
        if not wkt_geometria or not isinstance(wkt_geometria, str) or "S" in wkt_geometria:
            return ""

        try:
            import re
            import contextily as cx
            from shapely.wkb import loads as load_wkb
            from shapely.wkt import loads as load_wkt
            from shapely.ops import transform
            import pyproj

            geom_str = wkt_geometria.strip()
            if ";" in geom_str:
                geom_str = geom_str.split(";")[-1]

            # 1. Faz o parse inteligente da geometria transacional
            if re.match(r'^[0-9a-fA-F]+$', geom_str):
                poligono = load_wkb(geom_str, hex=True)
            else:
                poligono = load_wkt(geom_str)

            # 🚀 REPROJEÇÃO CRÍTICA: Transforma de EPSG:4326 (Lat/Lon) para EPSG:3857 (Web Mercator / Satélite)
            projeto = pyproj.Transformer.from_crs("epsg:4326", "epsg:3857", always_xy=True).transform
            poligono_projetado = transform(projeto, poligono)

            # Define dimensões rígidas proporcionais à caixa branca do PDF
            fig, ax = plt.subplots(figsize=(4, 2.5), dpi=180)

            # Determina as cores de borda com base no status regulatório (Com opacidade mais firme)
            status = str(status_vmg).upper().strip()
            if status in ['REPROVADO', 'NÃO APTO', 'NAO_CONFORME', 'DIVERGENTE']:
                cor_borda, cor_preenchimento = '#dc2626', '#ef4444'
            elif status in ['PENDENTE', 'EM ANÁLISE', 'ATENCAO']:
                cor_borda, cor_preenchimento = '#ea580c', '#f97316'
            else:
                cor_borda, cor_preenchimento = '#16a34a', '#22c55e' # Verde Agro

            # 2. Desenha o polígono real projetado no canvas gráfico
            if poligono_projetado.geom_type == 'Polygon':
                x, y = poligono_projetado.exterior.xy
                ax.fill(x, y, alpha=0.35, fc=cor_preenchimento, ec=cor_borda, lw=2, zorder=2)
            elif poligono_projetado.geom_type == 'MultiPolygon':
                for part in poligono_projetado.geoms:
                    x, y = part.exterior.xy
                    ax.fill(x, y, alpha=0.35, fc=cor_preenchimento, ec=cor_borda, lw=2, zorder=2)
            else:
                plt.close(fig)
                return ""

            # 🚀 INJEÇÃO DO SATÉLITE DE FUNDO: Consome os mesmos blocos Esri World Imagery do Angular
            try:
                cx.add_basemap(
                    ax,
                    source=cx.providers.Esri.WorldImagery,
                    zoom='auto',
                    zorder=1
                )
            except Exception as map_err:
                print(f"Aviso: Falha ao colar textura de satélite online, mantendo malha neutra: {str(map_err)}")
                ax.set_facecolor('#f8fafc')
                ax.grid(True, color='#e2e8f0', linestyle='--', linewidth=0.5)

            # Alinha os limites da câmera de forma justa ao redor das fronteiras da fazenda
            ax.axis('equal')
            limites = poligono_projetado.bounds # [minx, miny, maxx, maxy]
            margem_x = (limites[2] - limites[0]) * 0.15
            margem_y = (limites[3] - limites[1]) * 0.15
            ax.set_xlim(limites[0] - margem_x, limites[2] + margem_x)
            ax.set_ylim(limites[1] - margem_y, limites[3] + margem_y)

            # Oculta numerações cartográficas marginais para manter o visual limpo do relatório
            ax.get_xaxis().set_visible(False)
            ax.get_yaxis().set_visible(False)
            for spine in ax.spines.values():
                spine.set_visible(False)

            plt.tight_layout(pad=0)

            # Transforma a composição de Satélite + Polígono em Base64
            buf = io.BytesIO()
            plt.savefig(buf, format='png', bbox_inches='tight', pad_inches=0)
            buf.seek(0)
            image_base64 = base64.b64encode(buf.read()).decode('utf-8')

            plt.close(fig)
            return f"data:image/png;base64,{image_base64}"

        except Exception as error:
            print(f"Erro ao processar mapa satelitário composto: {str(error)}")
            return ""

    async def gerar_pdf_oficial_vmg(self, id_gleba: int) -> bytes:
        """
        Gera o binário do PDF do Atestado buscando dados reais agregados
        das tabelas de produção (agroprods) e auditoria (audit).
        """
        # 1. Recupera o payload estruturado do banco de dados de forma assíncrona
        async with self.db.begin():
            # Altere pelo método exato do seu repository
            raw_data = await self.repository.obter_dados_atestado_por_gleba(id_gleba)
            if not raw_data:
                return None

        # Converte o modelo Pydantic para dict se aplicável
        if hasattr(raw_data, "model_dump"):
            dados_payload = raw_data.model_dump()
        elif hasattr(raw_data, "dict"):
            dados_payload = raw_data.dict()
        else:
            dados_payload = raw_data


        poligono = loads(raw_data.get("coordenadas_raw"))
        centroide = poligono.centroid

        # 2. Resolução estrita do caminho absoluto da pasta de templates (Mesmo nível do service)
        path_templates = os.path.abspath(os.path.join(os.path.dirname(__file__), "templates"))

        # Leitura da Logo institucional convertida de forma segura para Base64
        logo_base64_src = ""
        path_logo = os.path.join(path_templates, "imagens", "logo.png")

        if os.path.exists(path_logo):
            try:
                with open(path_logo, "rb") as image_file:
                    logo_base64_src = f"data:image/png;base64,{base64.b64encode(image_file.read()).decode('utf-8')}"
            except Exception as e:
                print(f"Erro ao converter logo.png para Base64: {str(e)}")

        def formatar_numero_br(valor_raw) -> str:
            if valor_raw is None: return "0,00"
            try:
                return f"{float(valor_raw):,.2f}".replace(",", "v").replace(".", ",").replace("v", ".")
            except Exception: return str(valor_raw)

        wkt_real = dados_payload.get("coordenadas_raw") or  ""
        status_atual = dados_payload.get("status_atestado") or dados_payload.get("status_validacao") or "APROVADO"

        prod_declarada = float(dados_payload.get("volume_comercializar_declarado") or 20.00)
        prod_estimada_ia = float(dados_payload.get("produtividade_ia_sacas_ha") or dados_payload.get("estimativa_produtividade_sacas") or 56.11)
        ref_regional = float(dados_payload.get("referencia_regional_sacas_ha") or 76.00)

        # 2. Define a regra de negócio: Margem de tolerância admissível (ex: 20%)
        margem_tolerancia = 0.20
        diferenca_absoluta = abs(prod_declarada - prod_estimada_ia)

        # A produtividade estará CONFORME se a divergência entre o declarado e a IA
        # for menor ou igual à tolerância estipulada sobre a estimativa.
        if diferenca_absoluta <= (prod_estimada_ia * margem_tolerancia):
            produtividade_conforme_dinamica = True
        else:
            # Caso o produtor declare algo absurdamente fora do predito pela IA, vira divergente
            produtividade_conforme_dinamica = False

        # Validação extra de segurança: Se o declarado for maior que a referência histórica da região, bloqueia
        if prod_declarada > (ref_regional * 1.10):
            produtividade_conforme_dinamica = False

        # Processa a string Base64 do mapa dinâmico
        mapa_base64_src = self._gerar_imagem_mapa_base64(wkt_real, status_atual)

        eventos_raw = dados_payload.get("linha_tempo_safra") or []
        eventos_tratados = []
        for evento in eventos_raw:
            eventos_tratados.append({
                "fase": evento.get("fase", "Evento"),
                "data_evento": dados_payload.get("dt_estimada_plantio") ,
                "tipo": evento.get("tipo", "Estimado")
            })

        # 3. Compilação da árvore aninhada de chaves mapeadas com fallback seguro
        payload_estruturado = {
            "cabecalho": {
                "nome_gleba": dados_payload.get("cabecalho", {}).get("nome_gleba") or dados_payload.get("nome_gleba", "Fazenda Não Informada"),
                "cultura_principal": dados_payload.get("cabecalho", {}).get("cultura_principal") or dados_payload.get("cultura_principal", "Não Informada"),
                "safra": dados_payload.get("cabecalho", {}).get("safra") or dados_payload.get("safra", "N/A"),
                "periodo_analisado": dados_payload.get("cabecalho", {}).get("periodo_analisado") or dados_payload.get("periodo_analisado", "N/A"),
                "status_atestado": str(status_atual).upper(),
                "data_emissao_atestado": dados_payload.get("dt_emissao"),
                "area_hectares": formatar_numero_br(dados_payload.get("cabecalho", {}).get("area_hectares") or dados_payload.get("area_hectares", 0.0))
            },
            "conformidade": {
                "ambiental_conforme":  "Aprovado" if dados_payload.get("conforme_ambiental", dados_payload.get("conformidade", {}).get("conforme_ambiental", False)) else "Reprovado",
                "agricola_conforme": dados_payload.get("status_conducao"),

                "boas_praticas_conforme": "Aprovado" if dados_payload.get("possui_certificado_bpa", dados_payload.get("conformidade", {}).get("possui_certificado_bpa", False)) else "Pendente",
                "zarc_conforme": raw_data.get("validacao_zarc"),
                "produtividade_conforme":  produtividade_conforme_dinamica,

                "produtividade_estimada_sacas": formatar_numero_br(dados_payload.get("produtividade_estimada_sacas") or dados_payload.get("produtividade_ia_sacas_ha") or dados_payload.get("conformidade", {}).get("produtividade_estimada_sacas", 56.11)),
                "produtividade_declarada_sacas": formatar_numero_br(dados_payload.get("produtividade_declarada_sacas") or dados_payload.get("volume_comercializar_declarado") or dados_payload.get("conformidade", {}).get("produtividade_declarada_sacas", 20.0))
            },
            "informacoes_generais": {
                "municipio_uf": dados_payload.get("informacoes_generais", {}).get("municipio_uf") or dados_payload.get("municipio_uf", "Não Informado"),
                "codigo_car": dados_payload.get("informacoes_generais", {}).get("codigo_car") or dados_payload.get("codigo_car", "Não Informado"),
                "coordenadas_centroide": centroide,
                "data_cadastro": dados_payload.get("data_cadastro"),
                "mapa_base64": mapa_base64_src,
                "logo_base64": logo_base64_src
            },
            "linha_tempo_safra": eventos_tratados,
            "produtividade": {
                "declarado_sacas_ha": formatar_numero_br(dados_payload.get("produtividade", {}).get("declarado_sacas_ha") or dados_payload.get("declarado_sacas_ha", 60.0)),
                "estimado_ia_sacas_ha": formatar_numero_br(dados_payload.get("produtividade", {}).get("estimado_ia_sacas_ha") or dados_payload.get("estimado_ia_sacas_ha", 56.11)),
                "referencia_regional_sacas_ha": formatar_numero_br(dados_payload.get("referencia_regional_sacas_ha") or dados_payload.get("referencia_regional_sacas_ha", 76.0))
            },
            "metadados_atestado": {
                "codigo_atestado": dados_payload.get("metadados_atestado", {}).get("codigo_atestado") or dados_payload.get("codigo_atestado") or f"ATD-2025-{dados_payload.get('id_atestado', 0):06d}",
                "metodo_validacao": dados_payload.get("metadados_atestado", {}).get("metodo_validacao") or dados_payload.get("metodo_validacao", "VMG - Portaria SDI/MAPA nº 739/2025"),
                "orgao_emissor": dados_payload.get("metadados_atestado", {}).get("orgao_emissor") or dados_payload.get("orgao_emissor", "Secretaria de Inovação, Desenvolvimento Sustentável, Irrigação e Cooperativismo"),
                "validade_fim": dados_payload.get("dt_fim"),
                "hash_documento_blockchain": dados_payload.get("metadados_atestado", {}).get("hash_documento_blockchain") or dados_payload.get("hash_documento_blockchain") or dados_payload.get("hash_relatorio", "NÃO ASSINADO")
            }
        }

        # 4. Inicializa o motor Jinja2 e resolve a leitura do arquivo HTML
        env = Environment(loader=FileSystemLoader(path_templates))
        template = env.get_template("atestado_oficial_vmg.html")

        # Renderiza a string HTML injetando a árvore higienizada de dados
        html_renderizado = template.render(dados=payload_estruturado)

        # 5. Parâmetros de dimensionamento e codificação para o motor WebKit do wkhtmltopdf
        opcoes_pdf = {
            'page-size': 'A4',
            'margin-top': '12mm',
            'margin-right': '12mm',
            'margin-bottom': '15mm',
            'margin-left': '12mm',
            'encoding': "UTF-8",
            'no-outline': None,
            'quiet': ''
        }

        # Localizador de caminho absoluto para o binário nativo em ambiente Windows local
        caminho_windows = r'C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe'
        caminho_linux_debian = '/usr/bin/wkhtmltopdf'
        caminho_linux_local = '/usr/local/bin/wkhtmltopdf'

        if os.path.exists(caminho_windows):
            configuracao_motor = pdfkit.configuration(wkhtmltopdf=caminho_windows)
        elif os.path.exists(caminho_linux_debian):
            configuracao_motor = pdfkit.configuration(wkhtmltopdf=caminho_linux_debian)
        elif os.path.exists(caminho_linux_local):
            configuracao_motor = pdfkit.configuration(wkhtmltopdf=caminho_linux_local)
        else:
            # Fallback padrão do sistema operacional caso esteja mapeado nas variáveis globais (PATH)
            configuracao_motor = pdfkit.configuration()

        try:
            # Sela o documento gerando a cadeia de bytes estável do PDF em memória
            pdf_bytes = pdfkit.from_string(
                html_renderizado,
                False,
                options=opcoes_pdf,
                configuration=configuracao_motor
            )
            return pdf_bytes
        except Exception as e:
            print(f"Erro crítico na esteira de compilação pdfkit para a gleba {id_gleba}: {str(e)}")
            return None