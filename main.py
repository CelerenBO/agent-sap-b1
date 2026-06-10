# Copyright (c) Microsoft. All rights reserved.

import asyncio
import logging
import os
import sys

from agent_framework import Agent, MCPStreamableHTTPTool
from agent_framework._mcp import MCPTool
from agent_framework.foundry import FoundryChatClient
from agent_framework_foundry_hosting import ResponsesHostServer
from azure.identity import DefaultAzureCredential, ManagedIdentityCredential
from dotenv import load_dotenv


# --- logging estructurado ----
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s]%(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("agent.main")

# esta clase lo que hace es proporcionar compatibilidad con servidores MCP antiguos que usan SSE, ya que el framework de agentes actual esta optimizado para HTTP streamable 
# pero algunos endpoints legacy pueden seguir usando SSE, esta clase detecta eso y 
# se adapta para usar el transporte correcto segun la configuracion del URL del MCP. Revisar con enrique cualquier duda sobre esto =D
class MCPSSETool(MCPTool):

    def __init__(self, name: str, url: str, **kwargs):
        super().__init__(name=name, **kwargs)
        self.url = url

    def get_mcp_client(self):
        try:
            from mcp.client.sse import sse_client
        except ModuleNotFoundError as ex:
            raise ModuleNotFoundError("`mcp` is required to use `MCPSSETool`.") from ex

        return sse_client(url=self.url)


#  agregamos la configuracion para este proyecto 
load_dotenv()

REQUIRED_ENV_VARS = [
    "FOUNDRY_PROJECT_ENDPOINT",
    "AZURE_AI_MODEL_DEPLOYMENT_NAME",
    "MCP_SERVER_URL",
]

#prompt

SYSTEM_PROMPT = """
# Agente SAP Business One — Prompt del Sistema

## Rol y Propósito

Eres un asistente experto en **SAP Business One (SAP B1)**, diseñado para apoyar a equipos de **operaciones, ventas y ejecutivos** en la consulta y gestión de información empresarial en tiempo real. Tu misión es responder preguntas sobre clientes, facturas, cuentas por cobrar, inventario y artículos de manera precisa, rápida y útil, utilizando siempre las herramientas disponibles para obtener datos actualizados directamente del sistema SAP B1.

Eres parte de un sistema integrado con SAP Business One a través de un servidor MCP. Cada respuesta debe basarse **exclusivamente** en los datos obtenidos mediante las herramientas disponibles. Nunca inventes, asumas ni estimes datos de negocio.

---

## Herramientas Disponibles

| Herramienta | Uso |
|---|---|
| `search_customers` | Busca clientes por nombre, código o fragmento |
| `get_customer_balance` | Saldo actual de un cliente (total y vencido) |
| `get_ar_summary` | Resumen completo de CxC: saldo, facturas abiertas, total vencido |
| `get_open_invoices` | Lista de facturas abiertas de un cliente |
| `get_overdue_portfolio` | Todas las facturas vencidas de TODOS los clientes |
| `get_aging_report` | Reporte de antigüedad de saldos (30/60/90 días) |
| `get_customers_with_balance` | Lista clientes con saldo pendiente o morosos |
| `search_items` | Busca artículos/productos por nombre o descripción |
| `get_item` | Detalle completo de un artículo por código |
| `get_invoice_detail` | Detalle completo de una factura (líneas, cantidades, precios) |
| `get_out_of_stock_items` | Artículos agotados (stock = 0) |
| `get_low_stock_items` | Artículos con stock bajo un umbral mínimo |

---

## Reglas de Uso de Herramientas

### Clientes
1. **SIEMPRE** usa `search_customers` PRIMERO cuando el usuario mencione un cliente por nombre. Nunca asumas el código del cliente.
2. Si el usuario proporciona un código directamente (ej. "C0001"), usa `get_customer_balance` o `get_ar_summary` directamente.
3. Si `search_customers` devuelve múltiples resultados, presenta la lista y pide confirmación antes de continuar.
4. Si no hay resultados, informa con claridad y sugiere verificar el nombre.

### Cuentas por Cobrar (AR)
1. Para saldo/deuda de un cliente → usa `get_ar_summary` (panorama completo).
2. Para listar facturas específicas → usa `get_open_invoices`.
3. Para cartera vencida global → usa `get_overdue_portfolio`.
4. Para antigüedad de cartera → usa `get_aging_report`.
5. Para lista de clientes morosos → usa `get_customers_with_balance(overdue_only=true)`.

### Artículos e Inventario
1. **SIEMPRE** usa `search_items` PRIMERO cuando el usuario mencione un producto por nombre.
2. Si el usuario da un código (ej. "A00001"), usa `get_item` directamente.
3. Para stock agotado → usa `get_out_of_stock_items`.
4. Para stock bajo mínimo → usa `get_low_stock_items`.

---

## Reglas de Formato

1. **Tablas**: SIEMPRE usa tablas Markdown cuando presentes más de 2 registros.
2. **Moneda**: Formatea con símbolo y separadores de miles. Ej: `$1,234,567.89 MXN`.
3. **Fechas**: Usa formato `DD/MMM/YYYY` (ej. `15/ene/2025`).
4. **Porcentajes**: 1 decimal. Ej: `78.5%`.
5. **Códigos**: En formato `código` (monoespaciado).
6. **Alertas de vencimiento**: 🔴 >60 días, 🟡 30-60 días, 🟢 al corriente.

---

## Reglas de Seguridad

1. **NUNCA inventes datos**. Si una herramienta no devuelve datos, dilo explícitamente.
2. Si una herramienta falla, informa: "No pude obtener la información de SAP B1. El sistema reportó: [error]."
3. No repitas contraseñas, tokens ni configuración interna.
4. Si la consulta es ambigua, haz UNA pregunta de aclaración antes de ejecutar herramientas.

---

## Tono y Estilo

- **Idioma**: Responde SIEMPRE en español, a menos que el usuario escriba en otro idioma.
- **Tono**: Profesional pero amigable.
- **Concisión**: Directo y útil. Evita relleno.
- **Proactividad**: Sugiere la siguiente acción relevante cuando tenga sentido.

---

## Ejemplos de Respuestas Correctas

### Búsqueda de cliente por nombre
**Usuario**: "¿Qué me puedes decir del cliente Distribuidora Norte?"
**Agente**: Llama `search_customers("Distribuidora Norte")` → presenta resultado y pregunta qué información necesita.

### Consulta de saldo con alerta
**Usuario**: "¿Cuánto debe el cliente C0001?"
**Agente**: Llama `get_ar_summary("C0001")` → presenta saldo con indicador de vencimiento 🔴/🟡/🟢.

### Artículo no encontrado
**Usuario**: "Busca el artículo 'Laptopp Lenovo'"
**Agente**: Llama `search_items("Laptopp Lenovo")` → si no hay resultados, sugiere corrección ortográfica.

*Versión: 1.0 | Proyecto: SAP B1 AI Agent | Plataforma: Azure AI Foundry*
""".strip()

# validamos con esta funcion que todas las variables de entorno requeridas existan. revisar el .env.example atte: enrique
def validate_enviroment() -> None:
    missing = [ v for v in REQUIRED_ENV_VARS if not os.getenv(v)]
    if missing:
        logger.error("Variables de entorno faltantes: %s", missing)
        raise EnvironmentError(
            f"Configura las siguiente variables en el .env para que todo funcione correctamente: {missing}"
        )
    logger.info("Variables de entorno validadas correctamente. =D")

# seleccionamos la credencial segun el entorno. 
# - produccion : si estamos en produccion azure se usara managed identity credential porque es rapido 
#  - en desarrollo local: default azure credential

def get_credential():
    env = os.getenv("ENVIRONMENT", "development").lower()
    if env == "production":
        logger.info("Entorno de produccion detectado. Usando ManagedIdentityCredential.")
        return ManagedIdentityCredential()
    else:
        logger.info("Entorno de desarrollo detectado. Usando DefaultAzureCredential.")
        return DefaultAzureCredential()


def get_mcp_server_url() -> str:
    raw_url = os.getenv("MCP_SERVER_URL", "").strip()
    if not raw_url:
        raise EnvironmentError("MCP_SERVER_URL no está definido en el entorno.")
    return raw_url.rstrip("/")


def build_mcp_tool(name: str):
    url = get_mcp_server_url()
    if url.endswith("/sse"):
        logger.info("Usando transporte MCP SSE legacy para: %s", url)
        return MCPSSETool(name=name, url=url)

    logger.info("Usando transporte MCP streamable HTTP para: %s", url)
    return MCPStreamableHTTPTool(name=name, url=url)


# funcion para crear el agente  con el mcp server coneectado, este retorna el agente y el tool para gestionar su lifecycle.
async def build_agent(credential) -> tuple[Agent, MCPTool]:

    mcp_name = os.getenv("MCP_SERVER_NAME", "sap-b1-agent-mcp")
    mcp_url = get_mcp_server_url()

    logger.info("Conectando al MCP Server: %s -> %s", mcp_name, mcp_url)

    mcp_tool = build_mcp_tool(mcp_name)
    # aca tambien podemos restringir TOOL especificas del MCP si es necesario, descomenta cualquier duda preguntar a enrique =D:
    # allowed_tools=["get_customer_data", "get_invoice_data"],

    client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        credential=credential,
    )
    agent = Agent(
        client=client,
        name = os.getenv("AGENT_NAME", "sap-b1-agent"),
        instructions = SYSTEM_PROMPT,
        tools=[mcp_tool],
        default_options = {
            "store": False, # deshabilitamos el almacenamiento de conversaciones para proteger la privacidad de los datos de negocio, 
            #revisar con enrique si es necesario activar o usar otro mecanismo de almacenamiento seguro =D
            "temperature": float(os.getenv("AGENT_TEMPERATURE", "0.2")), # ajustamos la temperatura para respuestas mas coherentes y menos creativas, ideal para consultas de negocio
            "max_tokens": int(os.getenv("AGENT_MAX_TOKENS", "2048")), # limitamos los tokens para respuestas mas concisas y enfocadas
        },
    )

    logger.info("✅ Agente construido =D '%s' listo con MCP '%s'.", agent.name, mcp_name)
    return agent, mcp_tool

# esta funcion se encarga de iniciar el servidor del agente, es la que se llama en el main, separamos la logica para mantener el main limpio y organizado.
async def main_async():
    validate_enviroment()
    credential = get_credential()
    
    mcp_tool = build_mcp_tool(os.getenv("MCP_SERVER_NAME", "sap-b1-agent-mcp"))

    async with mcp_tool:
        client = FoundryChatClient(
            project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
            model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
            credential=credential,
        )
        agent = Agent(
            client=client,
            name = os.getenv("AGENT_NAME", "sap-b1-agent"),
            instructions = SYSTEM_PROMPT,
            tools=[mcp_tool],
            default_options = {
                "store": False, # deshabilitamos el almacenamiento de conversaciones para proteger la privacidad de los datos de negocio, 
                #revisar con enrique si es necesario activar o usar otro mecanismo de almacenamiento seguro =D
                "temperature": float(os.getenv("AGENT_TEMPERATURE", "0.2")), # ajustamos la temperatura para respuestas mas coherentes y menos creativas, ideal para consultas de negocio
                "max_tokens": int(os.getenv("AGENT_MAX_TOKENS", "2048")), # limitamos los tokens para respuestas mas concisas y enfocadas
            },
        )
        logger.info("🚀 Iniciando el server del agente =D")
        server = ResponsesHostServer(agent)
        await server.run_async()

def main():
    try:
        asyncio.run(main_async())
    except Exception as e:
        logger.critical("Error de configuracion: %s", e)
        sys.exit(1)  # Salir con codigo de error para indicar fallo en la configuración o ejecución del agente. Revisar el log para detalles.
    except KeyboardInterrupt:
        logger.info("Agente detenido manualmente. Chau! =D")
        sys.exit(0)  # Salir con codigo 0 para indicar que la detención fue intencional y no un error.
    except Exception as e:
        logger.exception("Error inesperadoal iniciar el agente: %s", e)
        sys.exit(1)  # Salir con codigo de error para indicar fallo en la ejecución del agente. Revisar el log para detalles.


if __name__ == "__main__":
    main()
