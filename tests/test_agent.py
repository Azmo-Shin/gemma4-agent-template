"""agent.py 단위 테스트 (가짜 client 로 LLM 없이 검증, 토큰 불필요)."""
import os
import types
import importlib
import pytest


# ── 모듈 import 안전성 (토큰 없어도 import 가능해야 함) ────────
def test_import_without_token(monkeypatch):
    monkeypatch.delenv("HF_TOKEN", raising=False)
    import agent
    importlib.reload(agent)              # SystemExit 없이 재로드돼야 함
    assert hasattr(agent, "agent_reply")


# ── .env 파서 ───────────────────────────────────────────────
def test_load_dotenv_parsing(tmp_path, monkeypatch):
    import agent
    monkeypatch.delenv("FOO", raising=False); monkeypatch.delenv("BAZ", raising=False)
    env = tmp_path / ".env"
    env.write_text('FOO="bar"\n# comment\nBAZ=qux\n', encoding="utf-8")
    agent._load_dotenv(str(env))
    assert os.environ["FOO"] == "bar" and os.environ["BAZ"] == "qux"


def test_load_dotenv_no_override(tmp_path, monkeypatch):
    import agent
    monkeypatch.setenv("FOO", "original")
    (tmp_path / ".env").write_text("FOO=changed\n", encoding="utf-8")
    agent._load_dotenv(str(tmp_path / ".env"))
    assert os.environ["FOO"] == "original"          # setdefault: 기존값 유지


def test_load_dotenv_non_utf8_tolerant(tmp_path):
    import agent
    env = tmp_path / ".env"
    env.write_bytes("# 허깅페이스 토큰\nK=v\n".encode("cp949"))   # 한글 Windows 인코딩
    agent._load_dotenv(str(env))                    # UnicodeDecodeError 로 죽지 않아야 함


# ── 가짜 OpenAI client ──────────────────────────────────────
def _tc(id, name, arguments):
    return types.SimpleNamespace(id=id, type="function",
                                 function=types.SimpleNamespace(name=name, arguments=arguments))

def _resp(content=None, tool_calls=None):
    msg = types.SimpleNamespace(content=content, tool_calls=tool_calls)
    return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)])

class FakeClient:
    def __init__(self, responses):
        self._responses = list(responses); self.calls = []
        self.chat = types.SimpleNamespace(
            completions=types.SimpleNamespace(create=self._create))
    def _create(self, **kwargs):
        self.calls.append(kwargs)
        return self._responses.pop(0) if self._responses else _resp(content="done")

def _schema(name):
    return {"type": "function", "function": {"name": name,
            "parameters": {"type": "object", "properties": {}}}}


# ── 도구 실행/에러 처리 ─────────────────────────────────────
def test_unknown_tool_returns_error_message():
    import agent
    client = FakeClient([_resp(tool_calls=[_tc("1", "ghost", "{}")]), _resp(content="ok")])
    messages = [{"role": "user", "content": "hi"}]
    out = agent.agent_reply(messages, client, tools=[_schema("x")], tool_funcs={})
    tool_msgs = [m for m in messages if m.get("role") == "tool"]
    assert len(tool_msgs) == 1 and tool_msgs[0]["tool_call_id"] == "1"
    assert "알 수 없는 도구" in tool_msgs[0]["content"] and out == "ok"


def test_tool_exception_does_not_orphan():
    import agent
    def boom(**kwargs):
        raise RuntimeError("kaboom")
    client = FakeClient([_resp(tool_calls=[_tc("42", "boom", "{}")]), _resp(content="recovered")])
    messages = [{"role": "user", "content": "hi"}]
    out = agent.agent_reply(messages, client, tools=[_schema("boom")], tool_funcs={"boom": boom})
    tool_ids = {m["tool_call_id"] for m in messages if m.get("role") == "tool"}
    assert "42" in tool_ids                          # 고아 tool_call 없음 (세션 안 깨짐)
    assert "오류" in [m for m in messages if m.get("role") == "tool"][0]["content"]
    assert out == "recovered"


def test_max_steps_caps_runaway_loop():
    import agent
    class AlwaysTool(FakeClient):
        def _create(self, **kwargs):
            self.calls.append(kwargs)
            return _resp(tool_calls=[_tc(f"c{len(self.calls)}", "noop", "{}")])
    client = AlwaysTool([])
    messages = [{"role": "user", "content": "hi"}]
    out = agent.agent_reply(messages, client, tools=[_schema("noop")],
                            tool_funcs={"noop": lambda **k: "ok"}, max_steps=5)
    assert len(client.calls) <= 5 and isinstance(out, str)   # 무한 루프 방지


def test_returns_empty_string_not_none():
    import agent
    client = FakeClient([_resp(content=None)])
    out = agent.agent_reply([{"role": "user", "content": "hi"}], client,
                            tools=[_schema("x")], tool_funcs={})
    assert out == ""                                 # None 반환 → "None" 출력 방지


def test_empty_tools_not_sent():
    import agent
    client = FakeClient([_resp(content="hi")])
    agent.agent_reply([{"role": "user", "content": "hi"}], client, tools=[], tool_funcs={})
    assert "tools" not in client.calls[0]            # 빈 배열이면 tools 아예 미전송


def test_large_tool_output_truncated():
    import agent
    big = "A" * 50000
    client = FakeClient([_resp(tool_calls=[_tc("1", "big", "{}")]), _resp(content="ok")])
    messages = [{"role": "user", "content": "hi"}]
    agent.agent_reply(messages, client, tools=[_schema("big")],
                      tool_funcs={"big": lambda **k: big})
    tool_msg = [m for m in messages if m.get("role") == "tool"][0]
    assert len(tool_msg["content"]) < len(big) and "잘림" in tool_msg["content"]
