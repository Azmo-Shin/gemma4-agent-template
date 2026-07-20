"""
Gemma 4 도구사용(Tool-Calling) 에이전트  ─  재사용 템플릿 [코어]
============================================================
이 파일은 '엔진'입니다. 거의 손댈 일이 없습니다.
▶ 새 기능을 붙이려면 → tools.py 에 도구 함수만 추가하세요. (README.md 참고)

실행:  python agent.py
종료:  exit / quit / 종료
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


# ── (선택) .env 파일에서 토큰 자동 로드 (없으면 환경변수 사용) ──
def _load_dotenv(path=".env"):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

_load_dotenv()

HF_TOKEN = os.environ.get("HF_TOKEN")
if not HF_TOKEN:
    raise SystemExit("⚠️  HF_TOKEN 이 없습니다. .env 파일 또는 환경변수로 설정하세요. (README 참고)")

client = OpenAI(base_url="https://router.huggingface.co/v1", api_key=HF_TOKEN)


# ── 에이전트 루프: 도구 호출이 없어질 때까지 반복 ───────────────
def agent_reply(messages):
    while True:
        resp = client.chat.completions.create(model=MODEL, messages=messages, tools=TOOLS)
        msg = resp.choices[0].message

        # 어시스턴트 응답(도구 요청 포함 가능)을 대화 기록에 추가
        assistant = {"role": "assistant", "content": msg.content or ""}
        if msg.tool_calls:
            assistant["tool_calls"] = [
                {"id": tc.id, "type": "function",
                 "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                for tc in msg.tool_calls
            ]
        messages.append(assistant)

        # 도구 요청이 없으면 → 최종 답변
        if not msg.tool_calls:
            return msg.content

        # 도구 실행 → 결과를 tool 메시지로 되먹임 → 루프 계속
        for tc in msg.tool_calls:
            name = tc.function.name
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            fn = TOOL_FUNCS.get(name)
            result = fn(**args) if fn else f"오류: 알 수 없는 도구 '{name}'"
            shown = ", ".join(f"{k}={v}" for k, v in args.items())
            print(f"   🔧 {name}({shown}) 실행")
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": str(result)})


def main():
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
            print(f"🤖 Gemma: {agent_reply(messages)}")
        except Exception as e:
            print(f"❌ 호출 실패: {e}  (401=토큰 / 402=크레딧 / 403=권한)")


if __name__ == "__main__":
    main()
