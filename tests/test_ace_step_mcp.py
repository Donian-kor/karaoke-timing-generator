# -*- coding: utf-8 -*-
"""ACE-Step Studio MCP 연동 및 DB 폴백 테스트."""

import json
import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from core import ace_step_mcp
from core.ace_step_integration import apply_lrc_to_ace


class FakeResponse:
    def __init__(self, payload, status_code=200, sse=False):
        body = json.dumps(payload, ensure_ascii=False)
        self.text = f"event: message\ndata: {body}\n\n" if sse else body
        self.status_code = status_code


def rpc_result(request, result=None, error=None):
    payload = {"jsonrpc": "2.0", "id": request["id"]}
    if error is not None:
        payload["error"] = error
    else:
        payload["result"] = result or {}
    return payload


SONG = {
    "id": "sid-1",
    "title": "테스트 곡",
    "lyrics": "old lyrics",
    "caption": "keep this",
    "metadata": {"bpm": 120, "has_karaoke": True},
}


class ParseBodyTest(unittest.TestCase):
    def test_json_and_sse(self):
        payload = {"jsonrpc": "2.0", "id": 1, "result": {"ok": True}}
        self.assertEqual(ace_step_mcp._parse_body(json.dumps(payload)), payload)
        self.assertEqual(
            ace_step_mcp._parse_body("event: message\ndata: " + json.dumps(payload) + "\n\n"),
            payload,
        )

    def test_invalid(self):
        with self.assertRaises(ace_step_mcp.AceStepMcpError):
            ace_step_mcp._parse_body("not json")


class McpClientTest(unittest.TestCase):
    def test_is_studio_available(self):
        def post(url, json=None, headers=None, timeout=None):
            tools = [{"name": "karaoke_set"}, {"name": "library_song_update"}]
            return FakeResponse(rpc_result(json, {"tools": tools}), sse=True)

        with patch.object(ace_step_mcp._session, "post", side_effect=post):
            self.assertTrue(ace_step_mcp.is_studio_available())

    def test_is_studio_available_missing_tools(self):
        def post(url, json=None, headers=None, timeout=None):
            return FakeResponse(rpc_result(json, {"tools": [{"name": "song_create"}]}))

        with patch.object(ace_step_mcp._session, "post", side_effect=post):
            self.assertFalse(ace_step_mcp.is_studio_available())

    def test_is_studio_available_connection_error(self):
        import requests

        with patch.object(
            ace_step_mcp._session, "post", side_effect=requests.ConnectionError("down")
        ):
            self.assertFalse(ace_step_mcp.is_studio_available())

    def test_set_lyrics_preserves_other_fields(self):
        calls = []

        def post(url, json=None, headers=None, timeout=None):
            name = json["params"]["name"]
            calls.append((name, json["params"].get("arguments")))
            if name == "library_song_get":
                return FakeResponse(rpc_result(json, {"structuredContent": dict(SONG)}))
            return FakeResponse(rpc_result(json, {"content": []}))

        with patch.object(ace_step_mcp._session, "post", side_effect=post):
            ace_step_mcp.set_lyrics("sid-1", "new lyrics")

        self.assertEqual([name for name, _ in calls], ["library_song_get", "library_song_update"])
        updated = calls[1][1]["song"]
        self.assertEqual(updated["lyrics"], "new lyrics")
        self.assertEqual(updated["caption"], "keep this")
        self.assertEqual(updated["metadata"], {"bpm": 120, "has_karaoke": True})

    def test_call_tool_raises_on_is_error(self):
        def post(url, json=None, headers=None, timeout=None):
            result = {"isError": True, "content": [{"type": "text", "text": "bad song id"}]}
            return FakeResponse(rpc_result(json, result))

        with patch.object(ace_step_mcp._session, "post", side_effect=post):
            with self.assertRaisesRegex(ace_step_mcp.AceStepMcpError, "bad song id"):
                ace_step_mcp.set_karaoke("sid-1", "[00:01.00]hi")


class ApplyIntegrationTest(unittest.TestCase):
    def test_mcp_path_does_not_touch_db(self):
        with (
            patch.object(ace_step_mcp, "is_studio_available", return_value=True),
            patch.object(ace_step_mcp, "set_lyrics") as set_lyrics,
            patch.object(ace_step_mcp, "set_karaoke") as set_karaoke,
        ):
            result = apply_lrc_to_ace(
                "sid-1", "[00:01.00]hi", "가사", "C:/nonexistent", "C:/nonexistent/db.sqlite"
            )

        self.assertEqual(result["method"], "mcp")
        self.assertTrue(result["karaoke_set"])
        self.assertTrue(result["lyrics_saved"])
        self.assertFalse(result["db_updated"])
        set_lyrics.assert_called_once_with("sid-1", "가사")
        set_karaoke.assert_called_once_with("sid-1", "[00:01.00]hi")

    def test_db_fallback(self):
        with tempfile.TemporaryDirectory() as media_dir:
            db_path = os.path.join(media_dir, "library.sqlite")
            conn = sqlite3.connect(db_path)
            conn.execute(
                "CREATE TABLE songs (id TEXT PRIMARY KEY, title TEXT, "
                "metadata_json TEXT, lyrics TEXT, updated_at TEXT)"
            )
            conn.execute(
                "INSERT INTO songs VALUES (?, ?, ?, ?, ?)",
                ("sid-1", "제목", "{}", "", ""),
            )
            conn.commit()
            conn.close()

            result = apply_lrc_to_ace(
                "sid-1", "[00:01.00]hi", "가사", media_dir, db_path, prefer_mcp=False
            )

            self.assertEqual(result["method"], "db")
            self.assertTrue(result["db_updated"])
            self.assertTrue(result["karaoke_set"])
            self.assertTrue(os.path.exists(os.path.join(media_dir, "sid-1.lrc")))

            conn = sqlite3.connect(db_path)
            meta_json, lyrics = conn.execute(
                "SELECT metadata_json, lyrics FROM songs WHERE id=?", ("sid-1",)
            ).fetchone()
            conn.close()
            self.assertEqual(json.loads(meta_json)["lrc"], "[00:01.00]hi")
            self.assertEqual(lyrics, "가사")


if __name__ == "__main__":
    unittest.main()
