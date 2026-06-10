# SAP B1 AI Agent

Este proyecto contiene un agente hospedado en Azure AI Foundry que ayuda a consultar información de SAP Business One a través de un servidor MCP.

## ¿Qué hace este agente?

El agente responde preguntas de negocio sobre:
- clientes
- saldo y cartera por cobrar
- facturas abiertas y vencidas
- inventario y artículos
- artículos agotados o con stock bajo

Para responder, usa herramientas expuestas por el servidor MCP conectado a SAP B1. Nunca inventa datos: siempre se apoya en los resultados que devuelve el MCP.

## Arquitectura

- `main.py`: punto de entrada del agente y conexión con Azure AI Foundry.
- `agent.yaml`: definición del agente hospedado para Foundry.
- `Dockerfile`: contenedor para despliegue.
- `requirements.txt`: dependencias de Python.
- `.env`: variables locales de configuración (no se sube a Git).

## Cómo funciona

1. El agente carga variables desde `.env`.
2. Crea un cliente de Azure AI Foundry con `FoundryChatClient`.
3. Conecta un MCP Tool al servidor SAP B1.
4. Expone el agente mediante `ResponsesHostServer` para que pueda ser invocado por Foundry o por el Agent Inspector.

## Requisitos

- Python 3.11
- Azure subscription con acceso a Foundry
- Proyecto Azure AI Foundry configurado
- Un servidor MCP que exponga las herramientas de SAP B1

## Variables de entorno

Crea un archivo `.env` con algo como esto:

```bash
FOUNDRY_PROJECT_ENDPOINT=https://<tu-proyecto>.services.ai.azure.com/api/projects/<id>
AZURE_AI_MODEL_DEPLOYMENT_NAME=gpt-4o
MCP_SERVER_URL=https://<tu-mcp>/sse
MCP_SERVER_NAME=sap-b1-mcp
AGENT_NAME=sap-b1-agent
AGENT_TEMPERATURE=0.2
AGENT_MAX_TOKENS=2048
ENVIRONMENT=development
```

> Importante: si tu MCP usa un endpoint SSE legacy, mantén `MCP_SERVER_URL` con `/sse`. Si tu MCP ya es streamable HTTP, usa `/mcp`.

## Ejecutar localmente

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

La app quedará disponible en:

```text
http://localhost:8088
```

## Probar con curl

```bash
curl -X POST http://localhost:8088/responses \
  -H "Content-Type: application/json" \
  -d '{"input":"Hola"}'
```

## Publicar en Azure AI Foundry

Sigue estos pasos en VS Code:

1. Instala la extensión **Foundry Toolkit**.
2. Abre la paleta de comandos (`Ctrl+Shift+P`).
3. Ejecuta **Foundry Toolkit: Deploy Hosted Agent**.
4. Selecciona tu proyecto de Foundry y tu suscripción.
5. Confirma el nombre del agente hospedado.
6. En la pantalla de variables de entorno, agrega al menos:
   - `FOUNDRY_PROJECT_ENDPOINT`
   - `AZURE_AI_MODEL_DEPLOYMENT_NAME`
   - `MCP_SERVER_URL`
   - `MCP_SERVER_NAME`
   - `AGENT_NAME`
7. Elige el método de despliegue (Code o Container) y haz clic en **Deploy**.

Después del despliegue, podrás abrir el agente desde el portal de Foundry o desde el playground del agente.

## Subir el proyecto a Git

Ejecuta estos comandos en la terminal (sin que yo los haga por ti):

```bash
git init
git add .
git commit -m "Primer commit del agente SAP B1"
git branch -M main
git remote add origin https://github.com/<tu-usuario>/<tu-repo>.git
git push -u origin main
```

Si ya tienes un repositorio remoto configurado, usa solo:

```bash
git add .
git commit -m "Actualiza agente SAP B1"
git push
```

## Recomendación para seguridad

- No subas el archivo `.env`.
- No subas tokens, secretos ni credenciales.
- Mantén el MCP Server y el modelo de Azure en variables de entorno.

## Nota importante

Este agente está pensado para consultar SAP B1 a través de herramientas MCP. Si cambias de endpoint MCP, revisa si debes usar `/sse` o `/mcp`.
