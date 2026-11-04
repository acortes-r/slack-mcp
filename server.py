"""MCP propio de Slack: leer conversaciones, enviar mensajes y subir archivos."""

import os
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

token = os.environ.get("SLACK_TOKEN")
if not token:
    raise SystemExit("Falta SLACK_TOKEN (xoxp-… para publicar como tú, xoxb-… como bot).")

slack = WebClient(token=token)
mcp = MCPServer(
    "slack-propio",
    instructions=(
        "Lee y escribe en Slack. Donde se pide una conversación se acepta un ID (C…/G…/D…), "
        "'#nombre-del-canal' o el correo de una persona (su DM contigo). Donde se pide un hilo "
        "se acepta su permalink. Las fechas aceptan ISO ('2026-11-01', '2026-11-01T09:00') o un ts de Slack."
    ),
)

CHANNEL_ID = re.compile(r"^[CGD][A-Z0-9]{6,}$")
PERMALINK = re.compile(r"/archives/([A-Z0-9]+)/p(\d{10})(\d{6})")
MENTION = re.compile(r"<@([UW][A-Z0-9]+)(?:\|[^>]*)?>")
SLACK_TS = re.compile(r"^\d{10}(\.\d+)?$")
_channels_by_name: dict[str, str] = {}
_user_names: dict[str, str] = {}
_workspace_url: str | None = None


def _call(method, **kwargs):
    try:
        return method(**kwargs)
    except SlackApiError as e:
        raise ToolError(f"Slack respondió {e.response['error']}") from e


def _resolve(destination: str) -> str:
    """Convierte un ID, '#canal' o un correo en el ID de conversación."""
    destination = destination.strip()
    if CHANNEL_ID.match(destination):
        return destination
    if "@" in destination and "." in destination.split("@")[-1]:
        user = _call(slack.users_lookupByEmail, email=destination)["user"]["id"]
        return _call(slack.conversations_open, users=user)["channel"]["id"]

    name = destination.lstrip("#").lower()
    if name not in _channels_by_name:
        cursor = None
        while True:
            r = _call(
                slack.conversations_list,
                types="public_channel,private_channel",
                exclude_archived=True,
                limit=1000,
                cursor=cursor,
            )
            _channels_by_name.update({c["name"]: c["id"] for c in r["channels"]})
            cursor = r.get("response_metadata", {}).get("next_cursor")
            if name in _channels_by_name or not cursor:
                break
    if name not in _channels_by_name:
        raise ToolError(f"No encontré el canal '{destination}' (o no tengo acceso a él).")
    return _channels_by_name[name]


def _parse_permalink(link: str) -> tuple[str, str] | None:
    """(canal, thread_ts) de un permalink; si es de una respuesta, toma el ts del padre."""
    if not (m := PERMALINK.search(link)):
        return None
    thread_ts = parse_qs(urlparse(link).query).get("thread_ts", [None])[0]
    return m.group(1), thread_ts or f"{m.group(2)}.{m.group(3)}"


def _target(destination: str | None, thread: str | None) -> tuple[str, str | None]:
    """Devuelve (canal, thread_ts). `thread` acepta un ts o el permalink de un mensaje."""
    if thread and (parsed := _parse_permalink(thread)):
        return parsed
    if not destination:
        raise ToolError("Indica `destination`, o un permalink en `thread`.")
    return _resolve(destination), thread


def _to_ts(value: str | None) -> str | None:
    """Convierte una fecha ISO (hora local si no trae zona) o un ts de Slack en ts."""
    if not value:
        return None
    if SLACK_TS.match(value):
        return value
    try:
        return str(datetime.fromisoformat(value).astimezone().timestamp())
    except ValueError as e:
        raise ToolError(f"Fecha inválida '{value}'; usa ISO, p. ej. 2026-11-01T09:00") from e


def _user_name(user_id: str) -> str:
    if user_id not in _user_names:
        try:
            u = slack.users_info(user=user_id)["user"]
            p = u.get("profile", {})
            _user_names[user_id] = p.get("display_name") or p.get("real_name") or u["name"]
        except SlackApiError:
            _user_names[user_id] = user_id
    return _user_names[user_id]


def _permalink(channel: str, ts: str, thread_ts: str | None = None) -> str:
    global _workspace_url
    if _workspace_url is None:
        _workspace_url = _call(slack.auth_test)["url"]
    link = f"{_workspace_url}archives/{channel}/p{ts.replace('.', '')}"
    if thread_ts and thread_ts != ts:
        link += f"?thread_ts={thread_ts}&cid={channel}"
    return link


def _message(m: dict, channel: str) -> dict:
    """Mensaje de Slack en forma legible: autor con nombre, menciones resueltas, fecha local."""
    author = (
        _user_name(m["user"])
        if m.get("user")
        else m.get("username") or m.get("bot_profile", {}).get("name", "bot")
    )
    out = {
        "ts": m["ts"],
        "at": datetime.fromtimestamp(float(m["ts"])).astimezone().isoformat(timespec="minutes"),
        "author": author,
        "text": MENTION.sub(lambda x: "@" + _user_name(x.group(1)), m.get("text", "")),
        "permalink": _permalink(channel, m["ts"], m.get("thread_ts")),
    }
    if m.get("reply_count"):
        out["replies"] = m["reply_count"]
    if m.get("files"):
        out["files"] = [f.get("name") or f.get("title") for f in m["files"]]
    if m.get("reactions"):
        out["reactions"] = {r["name"]: r["count"] for r in m["reactions"]}
    return out


def _paginate(method, key: str, limit: int, **kwargs) -> list[dict]:
    items, cursor = [], None
    while len(items) < limit:
        r = _call(method, limit=min(200, limit - len(items)), cursor=cursor, **kwargs)
        items.extend(r[key])
        cursor = r.get("response_metadata", {}).get("next_cursor")
        if not cursor:
            break
    return items[:limit]


@mcp.tool()
def list_conversations(
    query: str | None = None,
    kinds: str = "public_channel,private_channel",
    only_mine: bool = True,
    limit: int = 200,
) -> list[dict]:
    """Lista canales y conversaciones.

    query: filtra por texto en el nombre.
    kinds: separados por coma, de public_channel, private_channel, im (DMs), mpim (DMs grupales).
    only_mine: solo conversaciones donde eres miembro.
    """
    if only_mine:
        convs = _paginate(slack.users_conversations, "channels", 1000, types=kinds, exclude_archived=True)
    else:
        convs = _paginate(slack.conversations_list, "channels", 1000, types=kinds, exclude_archived=True)
    out = []
    for c in convs:
        name = f"DM con {_user_name(c['user'])}" if c.get("is_im") else c.get("name", c["id"])
        if query and query.lower() not in name.lower():
            continue
        item = {"id": c["id"], "name": name}
        if topic := c.get("topic", {}).get("value"):
            item["topic"] = topic
        out.append(item)
        if len(out) >= limit:
            break
    return out


@mcp.tool()
def read_conversation(
    conversation: str,
    since: str | None = None,
    until: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """Lee los mensajes de un canal o DM, del más antiguo al más reciente.

    Solo trae mensajes de primer nivel; los que tienen `replies` son hilos (léelos con read_thread
    pasando su permalink).
    conversation: ID, '#canal' o correo de una persona (DM).
    since / until: rango de fechas.
    """
    channel = _resolve(conversation)
    msgs = _paginate(
        slack.conversations_history, "messages", limit,
        channel=channel, oldest=_to_ts(since), latest=_to_ts(until),
    )
    return [_message(m, channel) for m in reversed(msgs)]


@mcp.tool()
def read_thread(thread: str, conversation: str | None = None, limit: int = 200) -> list[dict]:
    """Lee un hilo completo: el mensaje padre y sus respuestas.

    thread: permalink de cualquier mensaje del hilo, o el ts del padre (entonces indica conversation).
    """
    channel, thread_ts = _target(conversation, thread)
    msgs = _paginate(slack.conversations_replies, "messages", limit, channel=channel, ts=thread_ts)
    return [_message(m, channel) for m in msgs]


@mcp.tool()
def search_messages(query: str, count: int = 20, sort: str = "timestamp") -> list[dict]:
    """Busca mensajes en todo Slack (requiere user token).

    query: acepta la sintaxis de Slack: 'in:#canal', 'from:@persona', 'after:2026-11-01',
    'before:…', 'has:link', "frases entre comillas".
    sort: 'timestamp' (más recientes primero) o 'score' (relevancia).
    """
    r = _call(slack.search_messages, query=query, count=min(count, 100), sort=sort)
    out = []
    for m in r["messages"]["matches"]:
        item = _message(m, m["channel"]["id"])
        item["permalink"] = m["permalink"]
        item["channel"] = m["channel"].get("name") or m["channel"]["id"]
        out.append(item)
    return out


@mcp.tool()
def get_user(user: str) -> dict:
    """Perfil de una persona. user: su ID (U…) o su correo."""
    if "@" in user:
        u = _call(slack.users_lookupByEmail, email=user)["user"]
    else:
        u = _call(slack.users_info, user=user)["user"]
    p = u.get("profile", {})
    return {
        "id": u["id"],
        "name": p.get("display_name") or u["name"],
        "real_name": p.get("real_name"),
        "title": p.get("title"),
        "email": p.get("email"),
        "timezone": u.get("tz"),
        "status": " ".join(filter(None, [p.get("status_emoji"), p.get("status_text")])) or None,
    }


@mcp.tool()
def send_message(text: str, destination: str | None = None, thread: str | None = None) -> dict:
    """Envía un mensaje a Slack (acepta mrkdwn de Slack: *negrita*, _cursiva_, `código`, <url|texto>).

    destination: ID de canal, '#nombre' o correo de una persona (DM).
    thread: ts del mensaje padre, o su permalink (en ese caso destination se puede omitir).
    """
    channel, thread_ts = _target(destination, thread)
    r = _call(slack.chat_postMessage, channel=channel, text=text, thread_ts=thread_ts)
    link = _call(slack.chat_getPermalink, channel=channel, message_ts=r["ts"])["permalink"]
    return {"channel": channel, "ts": r["ts"], "permalink": link}


@mcp.tool()
def upload_file(
    path: str,
    destination: str | None = None,
    thread: str | None = None,
    comment: str | None = None,
    title: str | None = None,
) -> dict:
    """Sube un archivo local a Slack, opcionalmente con un mensaje.

    path: ruta del archivo en esta máquina.
    destination / thread: igual que en send_message.
    comment: texto que acompaña al archivo.
    """
    file = Path(path).expanduser()
    if not file.is_file():
        raise ToolError(f"No existe el archivo {file}")
    channel, thread_ts = _target(destination, thread)
    r = _call(
        slack.files_upload_v2,
        channel=channel,
        file=str(file),
        filename=file.name,
        title=title or file.name,
        initial_comment=comment,
        thread_ts=thread_ts,
    )
    info = r["file"]
    return {"channel": channel, "file_id": info["id"], "permalink": info.get("permalink")}


if __name__ == "__main__":
    mcp.run()
