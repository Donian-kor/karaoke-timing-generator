# -*- coding: utf-8 -*-
"""ACE-Step Studio 연동 유틸리티 (karaoke_gui.py에서 분리).

ACE-Step Studio SQLite DB에서 곡 목록과 LRC를 읽거나,
생성된 LRC를 ACE-Step Studio에 적용하는 순수 함수 모듈이다.
UI 의존성이 없으므로 단독 테스트가 가능하다.
"""

import json
import os
import shutil
import sqlite3
import datetime
import tempfile


def load_ace_songs(db_path: str) -> list:
    """ACE-Step Studio DB에서 곡 목록을 (id, title) 리스트로 반환한다."""
    if not os.path.exists(db_path):
        return []
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=5)
    rows = conn.execute("SELECT id, title FROM songs ORDER BY created_at DESC").fetchall()
    conn.close()
    return rows


def get_lrc_for_song(song_id: str, meta_json: str, media_dir: str) -> str:
    """선택한 곡에 저장된 LRC를 DB(metadata_json.lrc) → .lrc 파일 순서로 찾는다."""
    lrc = ""
    try:
        meta = json.loads(meta_json) if meta_json else {}
        lrc = (meta.get("lrc") or "").lstrip("\ufeff").strip()
    except Exception:
        pass
    if not lrc:
        lrc_path = os.path.join(media_dir, f"{song_id}.lrc")
        if os.path.exists(lrc_path):
            try:
                with open(lrc_path, encoding="utf-8-sig", errors="replace") as f:
                    lrc = f.read().strip()
            except Exception:
                pass
    return lrc


def apply_lrc_to_ace(song_id: str, lrc: str, lyrics_text: str, media_dir: str, db_path: str) -> dict:
    """LRC를 ACE-Step Studio에 적용한다. 결과 dict를 반환한다.

    Returns:
        dict with keys: target, db_updated, lyrics_saved, backup_created
    """
    result = {
        "target": os.path.join(media_dir, f"{song_id}.lrc"),
        "db_updated": False,
        "lyrics_saved": False,
        "backup_created": False,
    }
    target = result["target"]

    temp_path = None
    file_replaced = False
    target_existed = os.path.exists(target)
    conn = None
    try:
        descriptor, temp_path = tempfile.mkstemp(
            prefix=f".{song_id}.", suffix=".lrc.tmp", dir=media_dir
        )
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as f:
            normalized_lrc = lrc.replace("\r\n", "\n").replace("\r", "\n")
            f.write(normalized_lrc.replace("\n", "\r\n"))

        if target_existed:
            shutil.copy2(target, target + ".bak")
            result["backup_created"] = True

        if os.path.exists(db_path):
            backup_conn = None
            try:
                conn = sqlite3.connect(db_path, timeout=10)
                backup_conn = sqlite3.connect(db_path + ".bak")
                conn.backup(backup_conn)
            finally:
                if backup_conn is not None:
                    backup_conn.close()

            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT metadata_json FROM songs WHERE id=?", (song_id,)
            ).fetchone()
            if row is None:
                raise ValueError(f"선택한 곡을 데이터베이스에서 찾을 수 없습니다: {song_id}")
            meta = json.loads(row[0]) if row[0] else {}
            if not isinstance(meta, dict):
                raise ValueError("곡의 metadata_json 형식이 올바르지 않습니다.")
            meta["lrc"] = lrc
            if lyrics_text.strip():
                cursor = conn.execute(
                    "UPDATE songs SET metadata_json=?, lyrics=?, updated_at=? WHERE id=?",
                    (
                        json.dumps(meta, ensure_ascii=False),
                        lyrics_text,
                        datetime.datetime.now().isoformat(),
                        song_id,
                    ),
                )
                result["lyrics_saved"] = cursor.rowcount == 1
            else:
                conn.execute(
                    "UPDATE songs SET metadata_json=? WHERE id=?",
                    (json.dumps(meta, ensure_ascii=False), song_id),
                )
        os.replace(temp_path, target)
        temp_path = None
        file_replaced = True

        if conn is not None:
            conn.commit()
            result["db_updated"] = True
        result["lyrics_saved"] = bool(result["lyrics_saved"])
        return result
    except Exception as error:
        rollback_error = None
        if conn is not None:
            try:
                conn.rollback()
            except sqlite3.Error as rollback_failure:
                rollback_error = rollback_failure
        if file_replaced:
            try:
                if target_existed:
                    restore_path = target + ".restore"
                    shutil.copy2(target + ".bak", restore_path)
                    os.replace(restore_path, target)
                else:
                    os.remove(target)
            except OSError as restore_error:
                raise RuntimeError(
                    f"LRC 저장 실패 후 이전 파일을 복원하지 못했습니다: {restore_error}"
                ) from error
        if rollback_error is not None:
            raise RuntimeError(
                f"데이터베이스 변경을 되돌리지 못했습니다: {rollback_error}"
            ) from error
        raise
    finally:
        if conn is not None:
            conn.close()
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)
