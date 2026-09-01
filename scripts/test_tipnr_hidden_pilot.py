#!/usr/bin/env python3
"""Tests for the execution-ready, unexecuted Phase 8 TIPNR hidden pilot."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from tipnr_hidden_pilot_contract import (  # noqa: E402
    SAMPLE_IDS,
    SELECTION_SHA256,
    build_pilot_packet,
    pilot_packet_report,
)
from preview_tipnr_hidden_pilot import (  # noqa: E402
    build_pilot_preview,
    main as preview_main,
    write_new_pilot_preview,
)


EXPECTED_SELECTION = (
    ("person", "G0010", "5f791ad27a2902eb4422435b006cbb883899743b809f6786d7367d56183217b6"),
    ("person", "G0013", "f0b76e34a79d674af2d1362600b2b50bc63d7715e64a6c70e43dac4b35ff1565"),
    ("person", "G0078", "40c276c2fe9f9ee8fb54e9367953c3f3512be8218d56f143a8f82a446b16d4e5"),
    ("person", "G0107", "53988a7194f676b6b05db7f4fad96c9fd39d4e1821d3ac0087302c285b9cb2d7"),
    ("person", "G0132", "49c0e19a38133366a95c02ccaf036912c121692a98c5f9929a91aeb64f06e52d"),
    ("person", "G0207", "524273dd4cdb03f65a55eb1d05b5b4b84cacd46695058eb801005ec0362832fb"),
    ("person", "G0223G", "1037130044b799c3ac8e53248595278e2fc36210f54fb46873f218c6018ed5fa"),
    ("person", "G0223H", "1a8187197a906d2a7f2159b2d5a200ecaeb1cb068af85c2edc5d4aa0dd0a7255"),
    ("person", "G0223I", "71af8b3d2f8436c87836813f8b397051f7bbf15dba4461f637d4fdc4702927c1"),
    ("person", "G0223J", "3d965783438391d723cbaf1c3e4d52852f6fb45c8a6c0c6d3dbf41a54f8b1274"),
    ("place", "G0009", "b8db1dee76c7416fba5d45e3ad29f56951340cd4d23417c181364ed82b665614"),
    ("place", "G0098", "1ae34ab14cf2cda6ddf7928bcdf071cdcf4b4fbfe47862f44656cc6125fd6dd0"),
    ("place", "G0099", "4a034fd1f32510a0b56656ecd3c4b962de07dac64bb432073d624a43ea855698"),
    ("place", "G0116", "7b18e321b2ce1694ce2e5b08df32e4763f75626045cdebb184d310af30bfcb2d"),
    ("place", "G0137", "02c22cb23dfcd7855010bbc6478f9b82fc3516adfba4eb120c2215d917d906c3"),
    ("place", "G0222", "b5c77b572a3c906e9ab698f75a70892a5be0eb1734bf73733ea8397639a1c533"),
    ("place", "G0295", "bb0148822af539bab599009b7edcdbfc964f1907543971ddf22075e3ced2b326"),
    ("place", "G0490G", "379c668f35076ec02f97c9064088096d382a69f9bf74dbe86d1331e5c8c3d54f"),
    ("place", "G0490H", "2ed5af6fa2fe7126c2d992a3547255d28e8d231cc31f42abaf594532a1f39dd0"),
    ("place", "G0494", "28664288bc469b0f425f6855f909748296de5d1015821c5b99591acd107c9d24"),
)


def _artifact() -> Path:
    value = os.environ.get("TIPNR_TEST_ARTIFACT")
    if not value:
        raise unittest.SkipTest("TIPNR_TEST_ARTIFACT is not set")
    return Path(value)


class PilotPacketTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.packet = build_pilot_packet(ROOT, _artifact())

    def test_selects_exact_balanced_twenty_and_excludes_h0175(self) -> None:
        self.assertEqual(len(self.packet.items), 20)
        self.assertEqual(
            Counter(item.entity_type for item in self.packet.items),
            {"person": 10, "place": 10},
        )
        self.assertNotIn("H0175", [item.entity_id for item in self.packet.items])
        self.assertEqual(self.packet.selection_checksum, SELECTION_SHA256)
        self.assertEqual(
            tuple(
                (item.entity_type, item.entity_id, item.record["record_sha256"])
                for item in self.packet.items
            ),
            EXPECTED_SELECTION,
        )

    def test_projects_one_document_chunk_and_policy_per_item(self) -> None:
        self.assertEqual(len({item.document["id"] for item in self.packet.items}), 20)
        self.assertTrue(
            all(item.chunk["document_id"] == item.document["id"] for item in self.packet.items)
        )
        self.assertTrue(
            all(item.policy["chunk_id"] == item.chunk["id"] for item in self.packet.items)
        )
        self.assertTrue(
            all(item.policy["policy_class"] == "general_context" for item in self.packet.items)
        )

    def test_sample_and_serialized_packet_keep_only_approved_projection(self) -> None:
        self.assertEqual(self.packet.sample_ids, SAMPLE_IDS)
        report_text = repr(pilot_packet_report(self.packet)).lower()
        for excluded in ("briefest", "@brief", "@article", "@ambiguity", "relationship"):
            self.assertNotIn(excluded, report_text)


class PilotPreviewTests(unittest.TestCase):
    def test_preview_freezes_zero_effect_boundary(self) -> None:
        report = build_pilot_preview(ROOT, _artifact())
        self.assertIs(report["database_write_authorized"], False)
        self.assertIs(report["external_model_call_authorized"], False)
        self.assertEqual(report["counts"], {
            "items": 20, "documents": 20, "chunks": 20,
            "policy_rows": 20, "embedding_requests": 20,
        })
        self.assertEqual(report["maximum_spend_usd"], "0.01")
        self.assertEqual(report["reconciliation"], {
            "attempted": 20, "stored": 0, "errored": 0, "skipped": 20,
            "reason": "preview_only",
        })

    def test_preview_main_never_opens_network(self) -> None:
        with mock.patch("socket.socket", side_effect=AssertionError("network opened")):
            with mock.patch("sys.stdout"):
                self.assertEqual(preview_main(["--artifact", str(_artifact())]), 0)

    def test_preview_writer_is_create_new_and_byte_identical_only(self) -> None:
        local_root = ROOT / "local"
        local_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=local_root) as directory:
            target = Path(directory) / "preview.json"
            write_new_pilot_preview(target, b"same\n")
            write_new_pilot_preview(target, b"same\n")
            self.assertEqual(target.read_bytes(), b"same\n")
            with self.assertRaises(FileExistsError):
                write_new_pilot_preview(target, b"different\n")

    def test_preview_rejects_effect_and_selection_flags(self) -> None:
        for flag in ("--apply", "--limit", "--offset", "--entity-id"):
            with self.subTest(flag=flag), self.assertRaises(SystemExit):
                preview_main(["--artifact", str(_artifact()), flag, "1"])


if __name__ == "__main__":
    unittest.main()
