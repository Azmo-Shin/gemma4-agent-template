"""
Gemma 4 도구사용(Tool-Calling) 에이전트  ─  재사용 템플릿 [코어]
============================================================
이 파일은 '엔진'입니다. 거의 손댈 일이 없습니다.
▶ 새 기능을 붙이려면 → tools.py 에 도구 함수만 추가하세요. (README.md 참고)

실행:  python agent.py
종료:  exit / quit / 종료
테스트:  python -m pytest tests/     (토큰 없이 오프라인 검증)
"""

import os
import json
from openai import OpenAI

from tools import TOOLS, TOOL_FUNCS   # ← 도구는 전부 tools.py 에서 자동 로드

# ── 설정 ─────────────────────────────────────────────────────
MODEL = "google/gemma-4-31B-it:novita"   # :novita=Novita 지정 / 빼면 자동최속 / :cheapest=최저가
SYSTEM_PROMPT = (
    "너는 로컬 환경을 다룰 수 있는 한국어 AI 어시스턴트야. "
    "파일·데이터 관련 질문은 추측하지 말고, 제공된 도구를 호출해서 실제로 확인한 뒤 답해. "
    "답변은 간결하고 명확하게."
)
MAX_STEPS = 10                 # 한 턴에 허용하는 최대 도구 호출 라운드 (무한 루프·비용 폭주 방지)
MAX_TOOL_OUTPUT_CHARS = 20_000 # 도구 결과가 이보다 크면 잘라서 기록 (토큰 폭증 방지)


# ── (선택) .env 파일에서 토큰 자동 로드 ──────────────────────
def _load_dotenv(path=".env"):
    if os.path.exists(path):
        with open(path, encoding="utf-8", errors="replace") as f:   # 인코딩 관대(한글 .env도 OK)
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _make_client():
    """토큰을 확인하고 OpenAI 클라이언트를 만든다. (import 시점엔 호출하지 않아 테스트 가능)"""
    _load_dotenv()
    token = os.environ.get("HF_TOKEN")
    if not token:
        raise SystemExit("⚠️  HF_TOKEN 이 없습니다. .env 파일 또는 환경변수로 설정하세요. (README 참고)")
    return OpenAI(base_url="https://router.huggingface.co/v1", api_key=token)


def _run_tool(name, args, tool_funcs):
    """도구 하나를 안전하게 실행하고 결과 문자열을 반환. 예외는 문자열로 흡수(세션 파손 방지)."""
    fn = tool_funcs.get(name)
    if fn is None:
        return f"오류: 알 수 없는 도구 '{name}'"
    try:
        return str(fn(**args))
    except Exception as e:
        return f"오류: 도구 '{name}' 실행 실패: {e}"


# ── 에이전트 루프: 도구 호출이 없어질 때까지 (최대 max_steps) ──
def agent_reply(messages, client, *, model=MODEL, tools=None, tool_funcs=None, max_steps=MAX_STEPS):
    if tools is None:
        tools = TOOLS
    if tool_funcs is None:
        tool_funcs = TOOL_FUNCS

    for _ in range(max_steps):
        kwargs = {"model": model, "messages": messages}
        if tools:                                  # 빈 배열이면 tools 미전송 (API 400 방지)
            kwargs["tools"] = tools
        resp = client.chat.completions.create(**kwargs)
        msg = resp.choices[0].message

        # 어시스턴트 응답(도구 요청 포함 가능)을 대화 기록에 추가
        assistant = {"role": "assistant", "content": msg.content or ""}
        if msg.tool_calls:
            assistant["tool_calls"] = [
                {"id": tc.id, "type": "function",
                 "function": {"name": tc.function.name, "arguments": tc.function.arguments or "{}"}}
                for tc in msg.tool_calls
            ]
        messages.append(assistant)

        # 도구 요청이 없으면 → 최종 답변 (None 방지)
        if not msg.tool_calls:
            return msg.content or ""

        # 도구 실행 → 결과를 tool 메시지로 되먹임 (모든 tool_call 에 반드시 응답을 남김)
        for tc in msg.tool_calls:
            name = tc.function.name
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            result = _run_tool(name, args, tool_funcs)
            if len(result) > MAX_TOOL_OUTPUT_CHARS:                 # 거대 출력은 잘라서 기록
                result = result[:MAX_TOOL_OUTPUT_CHARS] + f"\n...[잘림: 전체 {len(result):,}자]"
            shown = ", ".join(f"{k}={v}" for k, v in args.items())
            print(f"   🔧 {name}({shown}) 실행")
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})

    # max_steps 초과 → 안전 종료 (무한 루프 대신 사용자에게 반환)
    return "⚠️ 도구 호출이 너무 많아 중단했습니다. 질문을 더 구체적으로 해주세요."


def main():
    client = _make_client()
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    print(f"💬 Gemma 4 에이전트 시작  |  도구 {len(TOOLS)}개 로드됨  (종료: exit/quit/종료)")
    print(f"📂 {os.getcwd()}")
    print("-" * 55)

    while True:
        try:
            user_input = input("\n🧑 나: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n👋 종료합니다.")
            break
        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit", "종료"):
            print("👋 종료합니다.")
            break

        messages.append({"role": "user", "content": user_input})
        try:
            print(f"🤖 Gemma: {agent_reply(messages, client)}")
        except Exception as e:
            print(f"❌ 호출 실패: {e}  (401=토큰 / 402=크레딧 / 403=권한)")


if __name__ == "__main__":
    main()
