import os
from mcp.server.fastmcp import FastMCP
from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException

mcp = FastMCP(
    "Google Ads MCP",
    stateless_http=True,
    json_response=True
)


def get_client():
    config = {
        "developer_token": os.environ["GOOGLE_ADS_DEVELOPER_TOKEN"],
        "client_id": os.environ["GOOGLE_ADS_CLIENT_ID"],
        "client_secret": os.environ["GOOGLE_ADS_CLIENT_SECRET"],
        "refresh_token": os.environ["GOOGLE_ADS_REFRESH_TOKEN"],
        "use_proto_plus": True,
    }

    login_customer_id = os.getenv("GOOGLE_ADS_LOGIN_CUSTOMER_ID")
    if login_customer_id:
        config["login_customer_id"] = login_customer_id.replace("-", "")

    return GoogleAdsClient.load_from_dict(config)


def customer_id():
    return os.environ["GOOGLE_ADS_CUSTOMER_ID"].replace("-", "")


@mcp.tool()
def listar_campanhas() -> str:
    """Lista as campanhas da conta Google Ads conectada."""
    client = get_client()
    service = client.get_service("GoogleAdsService")

    query = """
        SELECT
            campaign.id,
            campaign.name,
            campaign.status,
            campaign.advertising_channel_type,
            campaign_budget.amount_micros
        FROM campaign
        ORDER BY campaign.id
    """

    try:
        response = service.search(
            customer_id=customer_id(),
            query=query
        )

        linhas = []

        for row in response:
            budget = row.campaign_budget.amount_micros / 1_000_000

            linhas.append(
                f"ID: {row.campaign.id} | "
                f"Nome: {row.campaign.name} | "
                f"Status: {row.campaign.status.name} | "
                f"Tipo: {row.campaign.advertising_channel_type.name} | "
                f"Orçamento diário: R$ {budget:.2f}"
            )

        if not linhas:
            return "Nenhuma campanha encontrada."

        return "\n".join(linhas)

    except GoogleAdsException as ex:
        return f"Erro Google Ads: {ex}"


@mcp.tool()
def obter_desempenho(
    data_inicial: str,
    data_final: str
) -> str:
    """
    Consulta desempenho das campanhas.
    Datas no formato AAAA-MM-DD.
    """

    client = get_client()
    service = client.get_service("GoogleAdsService")

    query = f"""
        SELECT
            campaign.id,
            campaign.name,
            campaign.status,
            metrics.impressions,
            metrics.clicks,
            metrics.cost_micros,
            metrics.conversions,
            metrics.conversions_value
        FROM campaign
        WHERE segments.date BETWEEN '{data_inicial}' AND '{data_final}'
        ORDER BY metrics.cost_micros DESC
    """

    try:
        response = service.search(
            customer_id=customer_id(),
            query=query
        )

        linhas = []

        for row in response:
            custo = row.metrics.cost_micros / 1_000_000

            linhas.append(
                f"Campanha: {row.campaign.name} | "
                f"Impressões: {row.metrics.impressions} | "
                f"Cliques: {row.metrics.clicks} | "
                f"Custo: R$ {custo:.2f} | "
                f"Conversões: {row.metrics.conversions:.2f} | "
                f"Valor conversões: R$ {row.metrics.conversions_value:.2f}"
            )

        if not linhas:
            return "Nenhum dado encontrado para o período."

        return "\n".join(linhas)

    except GoogleAdsException as ex:
        return f"Erro Google Ads: {ex}"


@mcp.tool()
def alterar_status_campanha(
    campaign_id: str,
    novo_status: str,
    confirmar: bool = False
) -> str:
    """
    Altera o status de uma campanha.
    Status permitidos: ENABLED, PAUSED, REMOVED.
    A alteração só acontece se confirmar=True.
    """

    novo_status = novo_status.upper()

    if novo_status not in ["ENABLED", "PAUSED", "REMOVED"]:
        return "Status inválido. Use ENABLED, PAUSED ou REMOVED."

    if not confirmar:
        return (
            f"Solicitação preparada: campanha {campaign_id} "
            f"seria alterada para {novo_status}. "
            "Para executar, chame novamente com confirmar=True."
        )

    client = get_client()
    campaign_service = client.get_service("CampaignService")

    campaign_operation = client.get_type("CampaignOperation")

    resource_name = campaign_service.campaign_path(
        customer_id(),
        campaign_id
    )

    campaign_operation.update.resource_name = resource_name
    campaign_operation.update.status = getattr(
        client.enums.CampaignStatusEnum,
        novo_status
    )

    campaign_operation.update_mask.paths.append("status")

    try:
        response = campaign_service.mutate_campaigns(
            customer_id=customer_id(),
            operations=[campaign_operation]
        )

        return f"Campanha alterada com sucesso: {response.results[0].resource_name}"

    except GoogleAdsException as ex:
        return f"Erro Google Ads: {ex}"


@mcp.tool()
def alterar_orcamento(
    campaign_budget_id: str,
    novo_orcamento_diario: float,
    confirmar: bool = False
) -> str:
    """
    Altera o orçamento diário de uma campanha.
    Valor informado em reais.
    A alteração só acontece se confirmar=True.
    """

    if novo_orcamento_diario <= 0:
        return "O orçamento deve ser maior que zero."

    if not confirmar:
        return (
            f"Solicitação preparada: orçamento {campaign_budget_id} "
            f"seria alterado para R$ {novo_orcamento_diario:.2f} por dia. "
            "Para executar, chame novamente com confirmar=True."
        )

    client = get_client()
    budget_service = client.get_service("CampaignBudgetService")

    operation = client.get_type("CampaignBudgetOperation")

    resource_name = budget_service.campaign_budget_path(
        customer_id(),
        campaign_budget_id
    )

    operation.update.resource_name = resource_name
    operation.update.amount_micros = int(
        novo_orcamento_diario * 1_000_000
    )

    operation.update_mask.paths.append("amount_micros")

    try:
        response = budget_service.mutate_campaign_budgets(
            customer_id=customer_id(),
            operations=[operation]
        )

        return f"Orçamento alterado com sucesso: {response.results[0].resource_name}"

    except GoogleAdsException as ex:
        return f"Erro Google Ads: {ex}"


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))

    mcp.settings.host = "0.0.0.0"
    mcp.settings.port = port

    mcp.run(transport="streamable-http")
