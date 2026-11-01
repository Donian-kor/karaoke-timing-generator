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

    # 적용 전 백업 생성
    if os.path.exists(target):
        try:
            shutil.copy2(target, target + ".bak")
            result["backup_created"] = True
        except Exception:
            pass
    if os.path.exists(db_path):
        try:
            shutil.copy2(db_path, db_path + ".bak")
        except Exception:
            pass

    with open(target, "w", encoding="utf-8", newline="") as f:
        f.write(lrc.replace("\n", "\r\n"))

    # ACE-Step Studio는 metadata_json의 "lrc" 필드를 읽습니다.
    db_updated = False
    lyrics_saved = False
    if os.path.exists(db_path):
        try:
            conn = sqlite3.connect(db_path, timeout=10)
            cur = conn.cursor()
            row = cur.execute("SELECT metadata_json FROM songs WHERE id=?", (song_id,)).fetchone()
            if row is not None:
                meta = json.loads(row[0]) if row[0] else {}
                meta["lrc"] = lrc
                if lyrics_text.strip():
                    cur.execute(
                        "UPDATE songs SET metadata_json=?, lyrics=?, updated_at=? WHERE id=?",
                        (json.dumps(meta, ensure_ascii=False), lyrics_text, datetime.datetime.now().isoformat(), song_id),
                    )
                    lyrics_saved = True
                else:
                    cur.execute("UPDATE songs SET metadata_json=? WHERE id=?", (json.dumps(meta, ensure_ascii=False), song_id))
                conn.commit()
                db_updated = True
            conn.close()
        except Exception:
            pass

    result["db_updated"] = db_updated
    result["lyrics_saved"] = lyrics_saved
    return result
