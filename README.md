# slack-mcp

MCP propio para leer y escribir en Slack desde cualquier cliente MCP (Claude Code, Claude Desktop, Cursor, Codex, Gemini CLI, VS Code, OpenCode…).

## Tools

| Tool | Qué hace |
|---|---|
| `list_conversations(query?, kinds?, only_mine?, limit?)` | Lista canales, DMs y DMs grupales. |
| `read_conversation(conversation, since?, until?, limit?)` | Mensajes de un canal o DM en un rango de fechas. |
| `read_thread(thread, conversation?, limit?)` | Un hilo completo, a partir del permalink de cualquiera de sus mensajes. |
| `search_messages(query, count?, sort?)` | Búsqueda con la sintaxis de Slack (`in:#canal from:@persona after:2026-11-01`). |
| `get_user(user)` | Perfil de una persona por ID o correo. |
| `send_message(text, destination?, thread?)` | Publica un mensaje (mrkdwn de Slack) y devuelve su permalink. |
| `upload_file(path, destination?, thread?, comment?, title?)` | Sube un archivo local, con un mensaje opcional. |

Una conversación (`conversation`, `destination`) puede ser un ID (`C…`, `G…`, `D…`),
`#nombre-del-canal` o el correo de una persona (su DM contigo). Un hilo (`thread`) puede ser
el `ts` del mensaje padre o el permalink de cualquier mensaje del hilo; con permalink no hace
falta indicar la conversación. Las fechas aceptan ISO (`2026-11-01`, `2026-11-01T09:00`, en
hora local) o un `ts` de Slack.

Los mensajes vuelven con autor por nombre, menciones resueltas (`@ana`), fecha local,
permalink y, si aplica, número de respuestas, archivos y reacciones.

## 1. Crear la Slack app

En <https://api.slack.com/apps> → *Create New App* → *From a manifest*, elige el workspace y
pega:

```yaml
display_information:
  name: slack-mcp
oauth_config:
  scopes:
    user:
      # leer
      - channels:read
      - groups:read
      - im:read
      - mpim:read
      - channels:history
      - groups:history
      - im:history
      - mpim:history
      - search:read
      - users:read
      - users:read.email
      # escribir
      - chat:write
      - files:write
      - im:write
settings:
  org_deploy_enabled: false
  socket_mode_enabled: false
```

Instálala y copia el **User OAuth Token** (`xoxp-…`): lees lo mismo que ves tú en Slack y los
mensajes salen a tu nombre. Con un bot token (`xoxb-…`) el bot solo ve los canales a los que
lo invites, no ve tus DMs y `search_messages` no funciona.

Deja la app sin distribución pública: Slack limita mucho `conversations.history` y
`conversations.replies` en apps distribuidas fuera del Marketplace, pero no en apps internas
de un solo workspace.

## 2. Instalar

Necesitas Python 3.10 o superior. Cualquiera de estas deja disponible el comando `slack-mcp`:

```sh
pipx install git+https://github.com/acortes-r/slack-mcp
# o
uv tool install git+https://github.com/acortes-r/slack-mcp
```

Para no instalar nada, los clientes también pueden lanzarlo con
`uvx --from git+https://github.com/acortes-r/slack-mcp slack-mcp`.

Las apps de escritorio (Claude Desktop, Cursor) a veces no heredan el `PATH` de tu shell; si
no encuentran `slack-mcp`, usa la ruta absoluta que da `which slack-mcp`.

## 3. Registrar en tu cliente MCP

Es un servidor MCP estándar por **stdio**. En cualquier cliente se configura igual:

- comando: `slack-mcp`
- variables de entorno: `SLACK_TOKEN` (obligatoria) y `SLACK_READ_ONLY=1` (opcional)

**Claude Code**

```sh
claude mcp add slack --scope user -e SLACK_TOKEN=xoxp-... -- slack-mcp
```

**Claude Desktop, Cursor y Gemini CLI**: el mismo bloque en
`~/Library/Application Support/Claude/claude_desktop_config.json`, `~/.cursor/mcp.json` o
`~/.gemini/settings.json`, respectivamente:

```json
{
  "mcpServers": {
    "slack": {
      "command": "slack-mcp",
      "env": { "SLACK_TOKEN": "xoxp-..." }
    }
  }
}
```

**Codex** (`~/.codex/config.toml`)

```toml
[mcp_servers.slack]
command = "slack-mcp"
env = { SLACK_TOKEN = "xoxp-..." }
```

**VS Code** (`.vscode/mcp.json`)

```json
{
  "servers": {
    "slack": {
      "type": "stdio",
      "command": "slack-mcp",
      "env": { "SLACK_TOKEN": "xoxp-..." }
    }
  }
}
```

**OpenCode** (`opencode.json`)

```json
{
  "mcp": {
    "slack": {
      "type": "local",
      "command": ["slack-mcp"],
      "environment": { "SLACK_TOKEN": "xoxp-..." }
    }
  }
}
```

## Confirmación antes de escribir

Las tools de lectura se marcan con `readOnlyHint` y las de escritura (`send_message`,
`upload_file`) no; cada cliente decide con eso cuándo pedirte permiso, y no todos lo hacen.
Si tu cliente ejecuta las tools sin preguntar, o solo quieres leer, arranca el servidor con
`SLACK_READ_ONLY=1`: las tools de escritura ni siquiera se registran.

## Desarrollo

```sh
python3 -m venv .venv
.venv/bin/pip install -e .
SLACK_TOKEN=xoxp-... .venv/bin/slack-mcp
```
