import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from openai import OpenAI
from pydantic import BaseModel
from supabase import Client, create_client

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")
load_dotenv(BASE_DIR / ".env.local", override=True)

ALIYUN_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
ALIYUN_MODEL = "qwen3.5-flash-2026-02-23"
ALIYUN_API_KEY = os.environ.get("MY_API_KEY") or os.environ.get("ALIYUN_API_KEY")
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get(
    "SUPABASE_KEY"
)
supabase_client: Client | None = (
    create_client(SUPABASE_URL, SUPABASE_KEY)
    if SUPABASE_URL and SUPABASE_KEY
    else None
)


def is_public_supabase_key(key: str | None) -> bool:
    if not key:
        return False
    return key.startswith("sb_publishable_")

SYSTEM_PROMPT = (
    "你是一个充满赛博朋克神秘色彩的AI塔罗牌占卜师。用户会向你诉说迷茫。"
    "请你在心里随机抽取一张经典的塔罗牌，然后结合这张牌的牌意和用户的问题，"
    "给出一份赛博风、直指人心的解答。你的语气要神秘、高冷、充满哲理。"
    "请严格使用纯文本输出，格式必须完全遵循："
    "第一行：CARD: [卡牌名称]"
    "第二行：留空"
    "第三行开始：详细占卜解读（不少于150字）。"
    "不要输出JSON，不要输出Markdown标题，不要输出额外前缀。"
)

app = FastAPI(title="AI Tarot Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://aitarotsaas.vercel.app",
        "http://localhost:3000",
        "*",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class DrawCardRequest(BaseModel):
    question: str
    user_id: str


@app.get("/")
def root():
    return {"message": "Welcome to AI Tarot API"}


@app.post("/draw_card")
def draw_card(payload: DrawCardRequest):
    question = payload.question.strip()
    user_id = payload.user_id.strip()
    if not question:
        raise HTTPException(status_code=400, detail="question is required")
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id is required")

    if not supabase_client:
        raise HTTPException(
            status_code=500,
            detail="请先在环境变量中配置 SUPABASE_URL 和 SUPABASE_SERVICE_ROLE_KEY（或 SUPABASE_KEY）",
        )
    if is_public_supabase_key(SUPABASE_KEY):
        raise HTTPException(
            status_code=500,
            detail=(
                "Supabase Key 配置错误：当前是 sb_publishable 公钥，"
                "后端请改用 SUPABASE_SERVICE_ROLE_KEY（或旧版 service_role key）。"
            ),
        )

    try:
        quota_response = (
            supabase_client.table("user_quotas")
            .select("user_id,quota")
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        quota_rows = quota_response.data or []

        if not quota_rows:
            inserted_response = (
                supabase_client.table("user_quotas")
                .insert({"user_id": user_id, "quota": 3})
                .execute()
            )
            quota_rows = inserted_response.data or [{"user_id": user_id, "quota": 3}]

        quota = int(quota_rows[0].get("quota", 0))
    except Exception as exc:
        message = str(exc)
        if "row-level security policy" in message.lower():
            raise HTTPException(
                status_code=502,
                detail=(
                    "读取额度失败: Supabase RLS 拒绝访问 user_quotas。"
                    "请在后端环境变量使用 SUPABASE_SERVICE_ROLE_KEY，"
                    "或为当前 key 配置对应 RLS policy。"
                ),
            ) from exc
        raise HTTPException(status_code=502, detail=f"读取额度失败: {exc}") from exc

    if quota <= 0:
        def quota_exhausted_stream():
            yield "【命运的馈赠已达上限】您的免费占卜额度 (3次) 已用完。星辰需要休息，请期待后续商业版的解锁！"

        return StreamingResponse(
            quota_exhausted_stream(), media_type="text/plain; charset=utf-8"
        )

    if not ALIYUN_API_KEY:
        raise HTTPException(
            status_code=500, detail="请先在环境变量中配置 MY_API_KEY 或 ALIYUN_API_KEY"
        )

    try:
        (
            supabase_client.table("user_quotas")
            .update({"quota": quota - 1})
            .eq("user_id", user_id)
            .execute()
        )
    except Exception as exc:
        message = str(exc)
        if "row-level security policy" in message.lower():
            raise HTTPException(
                status_code=502,
                detail=(
                    "扣减额度失败: Supabase RLS 拒绝更新 user_quotas。"
                    "请在后端环境变量使用 SUPABASE_SERVICE_ROLE_KEY，"
                    "或为当前 key 配置对应 RLS policy。"
                ),
            ) from exc
        raise HTTPException(status_code=502, detail=f"扣减额度失败: {exc}") from exc

    try:
        client = OpenAI(api_key=ALIYUN_API_KEY, base_url=ALIYUN_BASE_URL)
        stream = client.chat.completions.create(
            model=ALIYUN_MODEL,
            stream=True,
            max_tokens=1200,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": question},
            ],
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"调用大模型失败: {exc}") from exc

    def iter_stream():
        try:
            for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta.content
                if delta:
                    yield delta
        except Exception as exc:
            yield f"\n\n[系统提示] 流式传输中断：{exc}"

    return StreamingResponse(iter_stream(), media_type="text/plain; charset=utf-8")
