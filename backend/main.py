import os
import re
from pathlib import Path
from typing import Any

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
    "解读必须自然完整收尾，最后一句必须是完整句，并以句号、问号或感叹号结束。"
    "不要输出JSON，不要输出Markdown标题，不要输出额外前缀。"
)

CONTINUATION_SYSTEM_PROMPT = (
    "你是同一个塔罗占卜师。你会接收一段已生成但可能被截断的占卜内容。"
    "请只输出新增的续写内容，不要重复已生成内容，不要重写 CARD 行。"
    "续写至少100字，并自然完整收尾。"
)

SENTENCE_ENDINGS = ("。", "！", "？", ".", "!", "?", "”", "」", "』", "）", ")")
CARD_HEADER_PATTERN = re.compile(
    r"^\s*CARD[:：]\s*\[?([^\]\r\n]+)\]?\s*\r?\n(?:\r?\n)?",
    flags=re.IGNORECASE,
)
MIN_MEANING_CHARS = 150
MAX_CONTINUATION_ROUNDS = 2


def extract_text(content: Any) -> str:
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        segments: list[str] = []
        for item in content:
            if isinstance(item, str):
                segments.append(item)
                continue

            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    segments.append(text)
                continue

            text = getattr(item, "text", None)
            if isinstance(text, str):
                segments.append(text)
                continue

            nested = getattr(item, "content", None)
            if isinstance(nested, str):
                segments.append(nested)

        return "".join(segments)

    return ""


def looks_incomplete(text: str) -> bool:
    cleaned = text.rstrip()
    if not cleaned:
        return False
    return not cleaned.endswith(SENTENCE_ENDINGS)


def strip_card_header(text: str) -> str:
    return CARD_HEADER_PATTERN.sub("", text, count=1).strip()


def parse_card_and_meaning(full_text: str) -> tuple[str, str]:
    normalized = full_text.replace("\uFEFF", "").strip()
    match = CARD_HEADER_PATTERN.match(normalized)
    if not match:
        return "未知卡牌", normalized

    card_name = (match.group(1) or "未知卡牌").strip() or "未知卡牌"
    meaning = normalized[match.end() :].strip()
    return card_name, meaning


def meaning_char_count(text: str) -> int:
    return len(re.sub(r"\s+", "", text))


def is_meaning_complete(text: str) -> bool:
    return meaning_char_count(text) >= MIN_MEANING_CHARS and not looks_incomplete(text)


def trim_overlap(base_text: str, new_text: str, max_overlap: int = 80) -> str:
    if not base_text or not new_text:
        return new_text

    overlap_limit = min(max_overlap, len(base_text), len(new_text))
    for size in range(overlap_limit, 0, -1):
        if base_text.endswith(new_text[:size]):
            return new_text[size:]
    return new_text


def request_continuation(
    client: OpenAI, question: str, card_name: str, current_meaning: str
) -> str:
    continuation_user_prompt = (
        f"用户问题：{question}\n"
        f"卡牌：{card_name}\n"
        f"当前已生成内容（可能被截断）：\n{current_meaning}\n\n"
        "请从最后一句自然续写，不要重复已有内容。"
    )

    response = client.chat.completions.create(
        model=ALIYUN_MODEL,
        max_tokens=1200,
        stream=False,
        messages=[
            {"role": "system", "content": CONTINUATION_SYSTEM_PROMPT},
            {"role": "user", "content": continuation_user_prompt},
        ],
    )
    if not response.choices:
        return ""

    message = response.choices[0].message
    raw_text = extract_text(message.content).replace("\uFEFF", "").strip()
    if not raw_text:
        return ""

    return strip_card_header(raw_text)

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
            max_tokens=1800,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": question},
            ],
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"调用大模型失败: {exc}") from exc

    def iter_stream():
        merged_chunks: list[str] = []
        finish_reason: str | None = None

        try:
            for chunk in stream:
                if not chunk.choices:
                    continue

                choice = chunk.choices[0]
                if choice.finish_reason:
                    finish_reason = choice.finish_reason

                delta_text = extract_text(choice.delta.content)
                if not delta_text:
                    continue

                merged_chunks.append(delta_text)
                yield delta_text

            final_text = "".join(merged_chunks).replace("\uFEFF", "").strip()
            if not final_text:
                return

            card_name, meaning_text = parse_card_and_meaning(final_text)
            need_continuation = finish_reason == "length" or not is_meaning_complete(
                meaning_text
            )
            continuation_round = 0

            while need_continuation and continuation_round < MAX_CONTINUATION_ROUNDS:
                try:
                    extra_text = request_continuation(
                        client=client,
                        question=question,
                        card_name=card_name,
                        current_meaning=meaning_text,
                    )
                except Exception:
                    break

                extra_text = extra_text.strip()
                if not extra_text:
                    break

                delta = trim_overlap(meaning_text, extra_text)
                if not delta:
                    break

                meaning_text += delta
                yield delta

                continuation_round += 1
                need_continuation = not is_meaning_complete(meaning_text)

            if looks_incomplete(meaning_text):
                yield "。"
            elif meaning_char_count(meaning_text) < MIN_MEANING_CHARS:
                yield "\n\n（命运信号暂告一段，如需更深层解析，可再次抽牌继续接收后续指引。）"
        except Exception as exc:
            yield f"\n\n[系统提示] 流式传输中断：{exc}"

    return StreamingResponse(iter_stream(), media_type="text/plain; charset=utf-8")
