# slack-mcp

MCP propio para leer y escribir en Slack desde Claude Code.

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

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## 3. Registrar en Claude Code

```sh
claude mcp add slack-propio --scope user -e SLACK_TOKEN=xoxp-... \
  -- ~/Projects/Personal/slack-mcp/.venv/bin/python ~/Projects/Personal/slack-mcp/server.py
```

## Confirmación antes de escribir

Las tools de lectura se marcan con `readOnlyHint` y las de escritura (`send_message`,
`upload_file`) no; cada cliente decide con eso cuándo pedirte permiso, y no todos lo hacen.
Si tu cliente ejecuta las tools sin preguntar, o solo quieres leer, arranca el servidor con
`SLACK_READ_ONLY=1`: las tools de escritura ni siquiera se registran.
