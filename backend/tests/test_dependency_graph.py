"""Dependency graph: the proof layer must cite real imports and nothing else."""

from core.dependency_graph import build_dependency_evidence


def _make_repo(tmp_path):
    (tmp_path / "services").mkdir()
    (tmp_path / "services" / "hotel_service.py").write_text("class HotelService:\n    pass\n")

    (tmp_path / "gateway").mkdir()
    (tmp_path / "gateway" / "api.py").write_text(
        "import os\nfrom services.hotel_service import HotelService\n"
    )
    (tmp_path / "gateway" / "admin.py").write_text("from services import hotel_service\n")

    java_dir = tmp_path / "src" / "main" / "java" / "com" / "app"
    java_dir.mkdir(parents=True)
    (java_dir / "HotelServiceImpl.java").write_text("package com.app;\npublic class HotelServiceImpl {}\n")
    (java_dir / "BookingController.java").write_text(
        "package com.app;\nimport com.app.HotelServiceImpl;\npublic class BookingController {}\n"
    )

    (tmp_path / "web").mkdir()
    (tmp_path / "web" / "booking.ts").write_text("const svc = require('../api/hotel_service');\n")
    (tmp_path / "web" / "unrelated.ts").write_text("import { x } from './other';\n")


def test_finds_dependents_across_languages(tmp_path):
    _make_repo(tmp_path)
    evidence = build_dependency_evidence(
        tmp_path,
        ["services/hotel_service.py", "src/main/java/com/app/HotelServiceImpl.java"],
    )

    assert evidence["available"] is True
    dependents = {edge["from_file"] for edge in evidence["edges"]}
    assert "gateway/api.py" in dependents
    assert "gateway/admin.py" in dependents
    assert "src/main/java/com/app/BookingController.java" in dependents
    assert "web/booking.ts" in dependents
    assert "web/unrelated.ts" not in dependents


def test_edges_carry_citations(tmp_path):
    _make_repo(tmp_path)
    evidence = build_dependency_evidence(tmp_path, ["services/hotel_service.py"])
    api_edge = next(e for e in evidence["edges"] if e["from_file"] == "gateway/api.py")
    assert api_edge["line"] == 2
    assert "hotel_service" in api_edge["code"]
    assert api_edge["to_file"] == "services/hotel_service.py"


def test_changed_files_dont_count_as_their_own_dependents(tmp_path):
    _make_repo(tmp_path)
    evidence = build_dependency_evidence(
        tmp_path, ["services/hotel_service.py", "gateway/api.py"]
    )
    assert all(edge["from_file"] != "gateway/api.py" for edge in evidence["edges"])


def test_non_source_changes_scan_cleanly(tmp_path):
    _make_repo(tmp_path)
    evidence = build_dependency_evidence(tmp_path, ["README.md", "config.yml"])
    assert evidence["available"] is True
    assert evidence["edges"] == []
    assert evidence["direct_dependents"] == 0


def test_missing_repo_fails_soft(tmp_path):
    evidence = build_dependency_evidence(tmp_path / "does-not-exist", ["a.py"])
    assert isinstance(evidence, dict)
    assert "available" in evidence
