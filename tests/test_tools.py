"""tools.py 단위 테스트 (오프라인, 토큰/네트워크 불필요)."""
import os
import pytest
import tools


# ── 레지스트리 계약 ──────────────────────────────────────────
def test_registry_in_sync():
    names = {t["function"]["name"] for t in tools.TOOLS}
    assert names == set(tools.TOOL_FUNCS)
    assert len(tools.TOOLS) == len(tools.TOOL_FUNCS)      # 이름 충돌로 조용히 덮이지 않음
    assert all(callable(f) for f in tools.TOOL_FUNCS.values())


def test_schema_required_contract():
    params = {t["function"]["name"]: t["function"]["parameters"] for t in tools.TOOLS}
    assert params["read_file"].get("required") == ["path"]
    assert "required" not in params["list_directory"]      # path 는 선택


def test_duplicate_tool_name_raises():
    with pytest.raises(ValueError):
        @tools.tool("read_file", "중복 이름")
        def _dup():
            return "x"


# ── get_current_directory ───────────────────────────────────
def test_get_current_directory():
    assert tools.get_current_directory() == os.getcwd()


# ── list_directory ──────────────────────────────────────────
def test_list_directory_labels(tmp_path, monkeypatch):
    monkeypatch.setattr(tools, "ALLOWED_ROOT", os.path.realpath(str(tmp_path)))
    (tmp_path / "sub").mkdir()
    (tmp_path / "f.txt").write_text("hi", encoding="utf-8")
    out = tools.list_directory(str(tmp_path))
    assert "[폴더] sub" in out and "[파일] f.txt" in out


def test_list_directory_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(tools, "ALLOWED_ROOT", os.path.realpath(str(tmp_path)))
    d = tmp_path / "empty"; d.mkdir()
    assert tools.list_directory(str(d)) == "(빈 폴더)"


def test_list_directory_error(tmp_path, monkeypatch):
    monkeypatch.setattr(tools, "ALLOWED_ROOT", os.path.realpath(str(tmp_path)))
    assert tools.list_directory(str(tmp_path / "nope")).startswith("오류:")


def test_list_directory_outside_root_denied(tmp_path, monkeypatch):
    root = tmp_path / "inside"; root.mkdir()
    monkeypatch.setattr(tools, "ALLOWED_ROOT", os.path.realpath(str(root)))
    assert tools.list_directory(str(tmp_path)).startswith("오류:")   # 상위 폴더 정찰 차단


# ── read_file ───────────────────────────────────────────────
def test_read_file_ok(tmp_path, monkeypatch):
    monkeypatch.setattr(tools, "ALLOWED_ROOT", os.path.realpath(str(tmp_path)))
    p = tmp_path / "a.txt"; p.write_text("hello", encoding="utf-8")
    assert tools.read_file(str(p)) == "hello"


def test_read_file_too_big(tmp_path, monkeypatch):
    monkeypatch.setattr(tools, "ALLOWED_ROOT", os.path.realpath(str(tmp_path)))
    monkeypatch.setattr(tools, "_MAX_BYTES", 10)
    p = tmp_path / "big.txt"; p.write_text("x" * 50, encoding="utf-8")
    assert tools.read_file(str(p)).startswith("오류: 파일이 너무 큽니다")


def test_read_file_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(tools, "ALLOWED_ROOT", os.path.realpath(str(tmp_path)))
    assert tools.read_file(str(tmp_path / "nope.txt")).startswith("오류:")


def test_read_file_outside_root_denied(tmp_path, monkeypatch):
    root = tmp_path / "inside"; root.mkdir()
    monkeypatch.setattr(tools, "ALLOWED_ROOT", os.path.realpath(str(root)))
    secret = tmp_path / "secret.txt"; secret.write_text("TOPSECRET", encoding="utf-8")
    out = tools.read_file(str(secret))
    assert out.startswith("오류:") and "TOPSECRET" not in out


def test_read_file_denylist_env(tmp_path, monkeypatch):
    monkeypatch.setattr(tools, "ALLOWED_ROOT", os.path.realpath(str(tmp_path)))
    p = tmp_path / ".env"; p.write_text("HF_TOKEN=leak", encoding="utf-8")
    out = tools.read_file(str(p))
    assert out.startswith("오류:") and "leak" not in out       # 비밀파일 차단


def test_read_file_binary_tolerant(tmp_path, monkeypatch):
    monkeypatch.setattr(tools, "ALLOWED_ROOT", os.path.realpath(str(tmp_path)))
    p = tmp_path / "b.bin"; p.write_bytes(b"\xff\xfe\x00abc")
    out = tools.read_file(str(p))
    assert isinstance(out, str) and not out.startswith("오류: 'utf-8'")  # errors='replace'


# ── run_tests (pytest 실행 도구) — subprocess 는 가짜로 대체 ──
def test_run_tests_registered():
    assert "run_tests" in tools.TOOL_FUNCS
    schema = [t for t in tools.TOOLS if t["function"]["name"] == "run_tests"][0]
    assert schema["function"]["parameters"]["properties"] == {}   # 모델이 인자 못 줌 (안전)


def test_run_tests_returns_output(monkeypatch):
    import subprocess
    fake = type("R", (), {"stdout": "24 passed in 0.5s\n", "stderr": ""})()
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: fake)
    assert "24 passed" in tools.run_tests()


def test_run_tests_truncates(monkeypatch):
    import subprocess
    fake = type("R", (), {"stdout": "X" * 5000, "stderr": ""})()
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: fake)
    assert len(tools.run_tests()) <= 2000


def test_run_tests_handles_error(monkeypatch):
    import subprocess
    def boom(*a, **k):
        raise RuntimeError("python 없음")
    monkeypatch.setattr(subprocess, "run", boom)
    assert tools.run_tests().startswith("오류:")
