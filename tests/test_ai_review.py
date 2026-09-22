import io
import json
import os
import tempfile
import unittest
import urllib.error
import wave
from dataclasses import asdict
from unittest.mock import MagicMock, patch

from engine import ai_review as ai
from engine.config import Config


PAYLOAD = {"evidence": [{"id": "T1", "kind": "transcript", "text": "অসমীয়া", "start_s": 1.0}],
           "report_language": "English"}


def response(findings=None, finish="stop"):
    result = {"summary": "Possible difference", "limitations": "Listen first",
              "findings": findings if findings is not None else [
                  {"severity": "warning", "explanation": "Check text", "evidence_ids": ["T1"], "suggestion": "Listen"}]}
    return {"model": "example/free-model", "choices": [{"finish_reason": finish,
             "message": {"content": json.dumps(result)}}]}


class OpenRouterTests(unittest.TestCase):
    def test_free_mode_blocks_paid_model_before_network(self):
        with patch.object(ai, "_request") as request:
            with self.assertRaises(ai.AIReviewError):
                ai.review("secret", "provider/paid", True, PAYLOAD)
            request.assert_not_called()

    def test_free_request_has_price_guard_and_no_paid_fallback(self):
        with patch.object(ai, "_request", return_value=response()) as request:
            result = ai.review("secret", "openrouter/free", True, PAYLOAD)
        endpoint, key, body = request.call_args.args
        self.assertEqual(endpoint, "/chat/completions")
        self.assertEqual(body["model"], "openrouter/free")
        self.assertEqual(body["provider"]["max_price"], {"prompt": 0, "completion": 0, "request": 0})
        self.assertEqual(body["provider"]["data_collection"], "deny")
        self.assertNotIn("models", body)
        self.assertNotIn("secret", json.dumps(body))
        self.assertEqual(body["messages"][1]["content"], ai.encode_payload(PAYLOAD))
        self.assertTrue(result["advisory_only"])
        self.assertEqual(len(result["findings"]), 1)

    def test_no_silent_context_truncation(self):
        with patch.object(ai, "_request") as request:
            with self.assertRaises(ai.AIReviewError):
                ai.review("secret", "openrouter/free", True, {"text": "x" * ai.MAX_PAYLOAD_BYTES})
            request.assert_not_called()

    def test_unknown_evidence_rejected(self):
        findings = [{"severity": "warning", "explanation": "check", "evidence_ids": ["T999"], "suggestion": "listen"}]
        with patch.object(ai, "_request", return_value=response(findings)):
            with self.assertRaises(ai.AIReviewError):
                ai.review("secret", "openrouter/free", True, PAYLOAD)

    def test_truncated_response_not_accepted_as_clean_report(self):
        with patch.object(ai, "_request", return_value=response([], finish="length")):
            with self.assertRaises(ai.AIReviewError):
                ai.review("secret", "openrouter/free", True, PAYLOAD)

    def test_extra_model_timestamps_discarded(self):
        findings = [{"severity": "warning", "explanation": "check", "evidence_ids": ["T1"],
                     "suggestion": "listen", "start_s": 999, "move_marker_to": 111}]
        with patch.object(ai, "_request", return_value=response(findings)):
            result = ai.review("secret", "openrouter/free", True, PAYLOAD)
        self.assertNotIn("start_s", result["findings"][0])
        self.assertNotIn("move_marker_to", result["findings"][0])

    def test_connection_sends_no_generation_or_chapter(self):
        with patch.object(ai, "_request", return_value={"data": {}}) as request:
            ai.test_connection("secret")
        request.assert_called_once_with("/key", "secret")

    def test_model_list_filters_paid_and_audio_only_models(self):
        entries = [
            {"id": "a/free:free", "pricing": {"prompt": "0", "completion": "0"}},
            {"id": "b/paid:free", "pricing": {"prompt": "1", "completion": "0"}},
            {"id": "c/audio:free", "pricing": {"prompt": "0", "completion": "0"}, "architecture": {"output_modalities": ["audio"]}},
            {"id": "d/missing:free"},
        ]
        with patch.object(ai, "_request", return_value={"data": entries}):
            self.assertEqual(ai.free_models(), ["openrouter/free", "a/free:free"])

    def test_http_error_does_not_echo_sensitive_body_or_key(self):
        opener = MagicMock()
        opener.open.side_effect = urllib.error.HTTPError("https://openrouter.ai", 429, "secret", {}, io.BytesIO(b"secret"))
        with patch("urllib.request.build_opener", return_value=opener):
            with self.assertRaises(ai.AIReviewError) as error:
                ai.test_connection("secret")
        self.assertIn("rate limit", str(error.exception))
        self.assertNotIn("secret", str(error.exception))

    def test_request_authorizes_header_only_and_disables_redirects(self):
        opener = MagicMock()
        opener.open.return_value.__enter__.return_value.read.return_value = b'{"data":{}}'
        with patch("urllib.request.build_opener", return_value=opener) as factory:
            ai.test_connection("secret")
        request = opener.open.call_args.args[0]
        self.assertEqual(request.full_url, ai.API_ROOT + "/key")
        self.assertEqual(request.get_header("Authorization"), "Bearer secret")
        self.assertIsNone(request.data)
        self.assertIsInstance(factory.call_args.args[0], ai._NoRedirect)

    def test_errors_in_success_http_response_rejected(self):
        opener = MagicMock()
        opener.open.return_value.__enter__.return_value.read.return_value = b'{"error":{"message":"secret"}}'
        with patch("urllib.request.build_opener", return_value=opener):
            with self.assertRaises(ai.AIReviewError):
                ai.test_connection("secret")


class LocalPreparationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = os.path.join(self.temp.name, "1CH_001.wav")
        with wave.open(self.path, "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(8000)
            handle.writeframes(b"\x00\x00" * 8000)

    def test_preparation_offline_and_original_untouched(self):
        with open(self.path, "rb") as handle:
            original = handle.read()
        cfg = Config(enable_script_verification=True, whisper_mode="api", openai_api_key="OLD_SECRET")
        with patch.object(ai, "_request") as request, patch("engine.loudness.ffmpeg_available", return_value=False):
            payload = ai.prepare_review(self.path, cfg, "Verse 1: অসমীয়া", "spoken words")
        request.assert_not_called()
        self.assertEqual(payload["book"], "1 Chronicles")
        self.assertEqual(payload["chapter"], 1)
        self.assertEqual(payload["transcript_source"], "user-pasted transcript (no verified timing)")
        text = ai.encode_payload(payload)
        self.assertNotIn("OLD_SECRET", text)
        self.assertNotIn(self.temp.name, text)
        self.assertNotIn("start_s", next(e for e in payload["evidence"] if e["id"] == "T1"))
        self.assertTrue(cfg.enable_script_verification)
        self.assertEqual(cfg.whisper_mode, "api")
        with open(self.path, "rb") as handle:
            self.assertEqual(original, handle.read())

    def test_invalid_transcript_time_does_not_become_playable(self):
        with patch.object(ai, "local_transcript", return_value=("local", [{"text": "hi", "start_s": -10, "end_s": 300}])), patch("engine.loudness.ffmpeg_available", return_value=False):
            payload = ai.prepare_review(self.path, Config(), "expected", transcribe=True)
        entry = next(e for e in payload["evidence"] if e["id"] == "T1")
        self.assertNotIn("start_s", entry)

    def test_missing_transcript_and_script_are_explicit(self):
        with patch("engine.loudness.ffmpeg_available", return_value=False):
            payload = ai.prepare_review(self.path, Config(), "")
        self.assertIn("No expected script", " ".join(payload["limitations"]))
        self.assertIn("No transcript", " ".join(payload["limitations"]))

    def test_config_never_contains_openrouter_key(self):
        cfg = Config(ai_review_model="provider/model:free")
        path = os.path.join(self.temp.name, "config.json")
        cfg.save(path)
        loaded = Config.load(path)
        self.assertEqual(loaded.ai_review_model, cfg.ai_review_model)
        self.assertTrue(loaded.ai_review_free_only)
        self.assertFalse(any("key" in field for field in asdict(cfg) if field.startswith("ai_review")))


if __name__ == "__main__":
    unittest.main()
