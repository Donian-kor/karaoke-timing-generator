# -*- coding: utf-8 -*-
"""Yue2 Studio 로컬 MCP 클라이언트 (구 ACE-Step Studio 자리).

Studio가 실행 중일 때 띄우는 ``http://127.0.0.1:8791/mcp`` (Streamable HTTP,
stateless JSON-RPC)를 호출해 공식 도구를 실행한다. DB를 직접 쓰지 않으므로
Studio를 종료할 필요가 없고, 변경 사항이 Studio 화면과 Activity에 즉시 반영된다.
"""

import json
import itertools

import requests

MCP_URL = "http://127.0.0.1:8791/mcp"
REQUIRED_TOOLS = {"karaoke_set", "library_song_update"}

# localhost 호출이 프록시 환경변수에 휩쓸리지 않도록 신뢰 환경을 끈 세션을 쓴다.
_session = requests.Session()
_session.trust_env = False
_ids = itertools.count(1)


class AceStepMcpError(RuntimeError):
    """MCP 호출 자체는 성공했지만 도구가 실패했거나 응답이 이상할 때."""


class StudioUnavailableError(AceStepMcpError):
    """Studio가 꺼져 있거나 MCP 서버에 연결할 수 없을 때."""


def _parse_body(text: str) -> dict:
    """JSON 또는 SSE(text/event-stream) 응답 본문에서 JSON-RPC 객체를 꺼낸다."""
    stripped = text.strip()
    if not stripped:
        return {}
    if stripped.startswith("{"):
        return json.loads(stripped)
    data_lines = [
        line[5:].strip()
        for line in stripped.splitlines()
        if line.startswith("data:")
    ]
    for chunk in reversed(data_lines):
        try:
            parsed = json.loads(chunk)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    raise AceStepMcpError("MCP 응답을 해석할 수 없습니다.")


def _format_error(error) -> str:
    if isinstance(error, dict):
        message = error.get("message", "")
        data = error.get("data")
        if data:
            return f"{message} ({data})" if message else str(data)
        return message or "알 수 없는 MCP 오류"
    return str(error)


def _post(method: str, params: dict, timeout: float) -> dict:
    payload = {
        "jsonrpc": "2.0",
        "id": next(_ids),
        "method": method,
        "params": params,
    }
    try:
        response = _session.post(
            MCP_URL,
            json=payload,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
            },
            timeout=timeout,
        )
    except requests.RequestException as exc:
        raise StudioUnavailableError(
            "Yue2 Studio에 연결할 수 없습니다. Studio가 실행 중인지 확인하세요."
        ) from exc

    if response.status_code >= 400:
        raise StudioUnavailableError(f"Yue2 Studio MCP 오류 (HTTP {response.status_code})")

    body = _parse_body(response.text)
    if "error" in body:
        raise AceStepMcpError(_format_error(body["error"]))
    result = body.get("result")
    return result if isinstance(result, dict) else {}


def _result_text(result: dict) -> str:
    parts = []
    for item in result.get("content") or []:
        if isinstance(item, dict) and item.get("type") == "text":
            parts.append(str(item.get("text", "")))
    return "\n".join(parts).strip()


def call_tool(name: str, arguments: dict | None = None, timeout: float = 15.0) -> dict:
    """MCP 도구를 호출하고 result 딕셔너리를 반환한다."""
    result = _post(
        "tools/call",
        {"name": name, "arguments": arguments or {}},
        timeout,
    )
    if result.get("isError"):
        raise AceStepMcpError(_result_text(result) or f"도구 실행 실패: {name}")
    return result


def is_studio_available(timeout: float = 2.0) -> bool:
    """Studio가 켜져 있고 필요한 가사편집 도구를 제공하는지 확인한다."""
    try:
        tools = _post("tools/list", {}, timeout)
    except AceStepMcpError:
        return False
    names = {
        tool.get("name")
        for tool in tools.get("tools", [])
        if isinstance(tool, dict)
    }
    return REQUIRED_TOOLS.issubset(names)


def list_songs() -> list:
    """라이브러리 곡을 (id, title) 리스트로 반환한다."""
    result = call_tool("library_songs_list", {})
    rows = result.get("structuredContent")
    if not isinstance(rows, list):
        rows = json.loads(_result_text(result) or "[]")
    return [
        (str(row["id"]), str(row.get("title") or ""))
        for row in rows
        if isinstance(row, dict) and row.get("id")
    ]


def set_karaoke(song_id: str, lrc: str) -> None:
    """공식 karaoke_set 도구로 LRC 타이밍을 설정한다."""
    call_tool("karaoke_set", {"song_id": song_id, "lrc": lrc})


def set_lyrics(song_id: str, lyrics: str) -> None:
    """공식 library_song_get/update 도구로 원본 가사 텍스트를 저장한다.

    library_song_update는 곡 객체 전체를 받으므로 기존 값을 먼저 읽어 가사만 바꿔
    되돌려 보낸다. 다른 필드(제목·caption·metadata)가 지워지지 않도록 한다.
    """
    result = call_tool("library_song_get", {"song_id": song_id})
    song = result.get("structuredContent")
    if not isinstance(song, dict):
        song = json.loads(_result_text(result) or "{}")
    if not isinstance(song, dict) or not song.get("id"):
        raise AceStepMcpError(f"곡 정보를 읽을 수 없습니다: {song_id}")
    song["lyrics"] = lyrics
    call_tool("library_song_update", {"song_id": song_id, "song": song})
