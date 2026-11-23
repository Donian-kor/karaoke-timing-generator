# -*- coding: utf-8 -*-
"""원본 가사 편집 시 LRC 보존 동작 테스트."""

import unittest

from core.lrc_parser import sync_plain_lrc_text


ENHANCED = "[00:09.66]<00:09.66>첫 <00:11.06>가사\n[00:14.84]<00:14.84>두 번째 <00:16.24>줄"
PLAIN = "[00:09.66]첫 가사\n[00:14.84]두 번째 줄"


class SyncPlainLrcTextTest(unittest.TestCase):
    def test_enhanced_lrc_is_never_modified(self):
        """단어 태그가 있는 생성 결과는 원본 가사를 편집해도 그대로여야 한다."""
        self.assertEqual(sync_plain_lrc_text(ENHANCED, ["새 가사"]), ENHANCED)
        self.assertEqual(
            sync_plain_lrc_text(ENHANCED, ["새 가사", "두 줄", "세 줄"]),
            ENHANCED,
        )

    def test_plain_lrc_text_updated_timestamps_preserved(self):
        result = sync_plain_lrc_text(PLAIN, ["고친 가사", "고친 두 번째"])
        self.assertEqual(
            result,
            "[00:09.66] 고친 가사\n[00:14.84] 고친 두 번째",
        )

    def test_line_count_mismatch_is_noop(self):
        self.assertEqual(sync_plain_lrc_text(PLAIN, ["한 줄만"]), PLAIN)
        self.assertEqual(
            sync_plain_lrc_text(PLAIN, ["1", "2", "3"]),
            PLAIN,
        )

    def test_empty_inputs_are_noop(self):
        self.assertEqual(sync_plain_lrc_text(PLAIN, []), PLAIN)
        self.assertEqual(sync_plain_lrc_text("", ["가사"]), "")
        self.assertEqual(sync_plain_lrc_text("   ", ["가사"]), "   ")


if __name__ == "__main__":
    unittest.main()
