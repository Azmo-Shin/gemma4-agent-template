"""
[STEP 1] 가장 단순한 예제 — Gemma 4 를 '한 번' 호출하기.
============================================================
이 파일로 "어떻게 모델을 부르는가" 핵심만 이해하면 된다. (딱 3단계)
   ① 클라이언트 만들기(주소 + 토큰) → ② 메시지 보내기 → ③ 답 출력

도구까지 쓰는 완성형(파일 읽기 등)은 → agent.py + tools.py 참고.

실행:  python test_gemma4.py     (HF_TOKEN 을 setx 또는 .env 로 설정해둔 상태)
"""

import os
from openai import OpenAI

# ① 클라이언트: HuggingFace 라우터 주소 + 토큰 (OpenAI SDK 그대로 사용)
client = OpenAI(
    base_url="https://router.huggingface.co/v1",
    api_key=os.environ.get("HF_TOKEN", ""),
)

# ② 메시지 보내기
resp = client.chat.completions.create(
    model="google/gemma-4-31B-it:novita",   # :novita = Novita 제공자로 라우팅
    messages=[
        {"role": "user", "content": "자기소개를 한 문장으로 해줘."},
    ],
)

# ③ 답 출력
print("🤖", resp.choices[0].message.content)
