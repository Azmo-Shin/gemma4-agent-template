"""
도구 정의  ─  ★★★ 이 파일이 '확장 지점' 입니다 ★★★
============================================================
새 기능을 추가하려면 → 아래처럼 함수 하나 + @tool 데코레이터만 붙이면 끝.
agent.py 코어는 손댈 필요 없이 자동으로 인식합니다.

    @tool("도구이름",
          "무슨 일을 하는지 설명 (모델이 이걸 읽고 '언제 이 도구를 쓸지' 판단함)",
          parameters={"인자명": {"type": "string", "description": "인자 설명"}},
          required=["인자명"])
    def 도구이름(인자명):
        ...                    # 실제로 실행할 파이썬 코드
        return "결과 문자열"     # 반드시 문자열(또는 str()로 변환되는 값) 반환

⚠️ 안전 원칙: 도구의 '권한'은 전적으로 여기서 당신이 정합니다.
   모델은 '요청'만 할 뿐, 실제 실행 여부·범위는 이 코드가 결정합니다.
   - 파일 도구는 ALLOWED_ROOT 트리 안으로만 제한되고 비밀파일(.env 등)은 차단됩니다.
   - 이름이 겹치는 도구를 등록하면 조용히 덮이지 않고 즉시 ValueError 로 알립니다.
"""

import os

# ── 안전장치 설정 ────────────────────────────────────────────
_MAX_BYTES = 100_000                              # read_file 최대 크기
ALLOWED_ROOT = os.path.realpath(os.getcwd())      # 파일 접근 허용 루트 (이 밖은 거부; 필요시 넓히세요)
_DENY_NAMES = {".env"}                             # 차단할 비밀 파일명
_DENY_SUFFIXES = (".pem", ".key")                 # 차단할 확장자
_DENY_CONTAINS = ("id_rsa",)                       # 이름에 포함되면 차단


# ── 도구 등록 장치 (수정할 필요 없음) ────────────────────────
_REGISTRY = []

def tool(name, description, parameters=None, required=None):
    if any(s["function"]["name"] == name for s, _ in _REGISTRY):
        raise ValueError(f"중복된 도구 이름: {name!r} (이미 등록됨)")   # 조용한 덮어쓰기 방지
    params = {"type": "object", "properties": parameters or {}}
    if required:
        params["required"] = required
    schema = {"type": "function",
              "function": {"name": name, "description": description, "parameters": params}}
    def deco(fn):
        _REGISTRY.append((schema, fn))
        return fn
    return deco


def _safe_path(path):
    """ALLOWED_ROOT 트리 안이고 비밀파일이 아니면 실제경로를, 아니면 None 을 반환."""
    full = os.path.realpath(path)
    root = os.path.realpath(ALLOWED_ROOT)
    if full != root and not full.startswith(root + os.sep):
        return None                                # 루트 밖 (상위폴더/절대경로 정찰 차단)
    base = os.path.basename(full).lower()
    if base in _DENY_NAMES or base.endswith(_DENY_SUFFIXES) or any(x in base for x in _DENY_CONTAINS):
        return None                                # 비밀 파일 차단
    return full


# ════════════════════════════════════════════════════════════
#  현재 활성 도구 — 파일 시스템 (읽기 전용, 프로젝트 폴더로 제한)
# ════════════════════════════════════════════════════════════

@tool("get_current_directory", "현재 작업 디렉토리(절대경로)를 반환한다.")
def get_current_directory():
    return os.getcwd()


@tool("list_directory", "지정 경로의 파일/폴더 목록을 반환한다. path 생략 시 현재 폴더.",
      parameters={"path": {"type": "string", "description": "조회할 경로 (기본 '.')"}})
def list_directory(path="."):
    safe = _safe_path(path)
    if safe is None:
        return "오류: 접근이 허용되지 않은 경로입니다 (프로젝트 폴더 밖)."
    try:
        rows = []
        for n in sorted(os.listdir(safe)):
            full = os.path.join(safe, n)
            rows.append(f"[폴더] {n}" if os.path.isdir(full)
                        else f"[파일] {n} ({os.path.getsize(full):,} bytes)")
        return "\n".join(rows) or "(빈 폴더)"
    except Exception as e:
        return f"오류: {e}"


@tool("read_file", "지정한 텍스트 파일의 내용을 반환한다.",
      parameters={"path": {"type": "string", "description": "읽을 파일 경로"}},
      required=["path"])
def read_file(path):
    safe = _safe_path(path)
    if safe is None:
        return "오류: 접근이 허용되지 않은 경로입니다 (프로젝트 폴더 밖 또는 비밀 파일)."
    try:
        if os.path.getsize(safe) > _MAX_BYTES:
            return f"오류: 파일이 너무 큽니다(>{_MAX_BYTES:,} bytes)."
        with open(safe, encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception as e:
        return f"오류: {e}"


# ════════════════════════════════════════════════════════════
#  확장 예시 — 필요할 때 주석(#)만 풀어서 사용하세요.
#  (각 예시는 README.md '확장 아이디어'에 설명 있음)
#  ※ 파일을 다루는 도구를 추가할 땐 위 _safe_path() 로 경로를 제한하세요.
# ════════════════════════════════════════════════════════════

# # ── [1] 오늘 날짜 ── LLM은 현재 시각을 모름 → "이번 달/오늘" 계산에 필수
# from datetime import datetime
# @tool("get_current_datetime", "현재 날짜와 시각을 반환한다.")
# def get_current_datetime():
#     return datetime.now().strftime("%Y-%m-%d %H:%M:%S (%A)")


# # ── [2] CSV/Excel 읽기 ──  pip install pandas openpyxl
# @tool("read_table", "CSV/Excel 파일을 읽어 요약(행수·컬럼·앞부분 10행)을 반환한다.",
#       parameters={"path": {"type": "string", "description": "csv 또는 xlsx 경로"}},
#       required=["path"])
# def read_table(path):
#     safe = _safe_path(path)
#     if safe is None:
#         return "오류: 접근이 허용되지 않은 경로입니다."
#     import pandas as pd
#     df = pd.read_excel(safe) if safe.lower().endswith((".xlsx", ".xls")) else pd.read_csv(safe)
#     return (f"{len(df)}행 x {len(df.columns)}열\n컬럼: {list(df.columns)}\n\n"
#             f"{df.head(10).to_string()}")


# # ── [3] DB 조회 (읽기 전용) ──  pip install mysql-connector-python
# #     SELECT만 허용하도록 막아둔 안전 예시. 접속정보는 .env(환경변수)로.
# @tool("run_sql", "데이터베이스에 SELECT 쿼리를 실행하고 결과를 반환한다. (읽기 전용)",
#       parameters={"query": {"type": "string", "description": "실행할 SELECT SQL"}},
#       required=["query"])
# def run_sql(query):
#     import mysql.connector
#     if not query.strip().lower().startswith("select"):
#         return "오류: 안전을 위해 SELECT 쿼리만 허용됩니다."
#     conn = mysql.connector.connect(
#         host=os.environ["DB_HOST"], user=os.environ["DB_USER"],
#         password=os.environ["DB_PASSWORD"], database=os.environ["DB_DATABASE"])
#     try:
#         cur = conn.cursor()
#         cur.execute(query)
#         cols = [d[0] for d in cur.description]
#         rows = cur.fetchmany(50)          # 최대 50행만
#         return " | ".join(cols) + "\n" + "\n".join(str(r) for r in rows)
#     finally:
#         conn.close()


# # ── [4] 결과 파일로 저장 ── (쓰기 도구: 신중히, 경로 제한 필수)
# @tool("write_file", "텍스트를 파일로 저장한다.",
#       parameters={"path": {"type": "string"}, "content": {"type": "string"}},
#       required=["path", "content"])
# def write_file(path, content):
#     safe = _safe_path(path)
#     if safe is None:
#         return "오류: 접근이 허용되지 않은 경로입니다."
#     with open(safe, "w", encoding="utf-8") as f:
#         f.write(content)
#     return f"저장 완료: {safe} ({len(content):,}자)"


# ── agent.py 가 읽어가는 최종 구조 (수정 불필요) ──────────────
TOOLS = [schema for schema, _ in _REGISTRY]
TOOL_FUNCS = {schema["function"]["name"]: fn for schema, fn in _REGISTRY}
