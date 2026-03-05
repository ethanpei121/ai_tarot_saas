import logging
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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("tarot")

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

REPAIR_SYSTEM_PROMPT = (
    "你是一个严谨的塔罗编辑器。你会收到一段可能不完整、语义断裂或格式错误的占卜草稿。"
    "请将其修复为完整、连贯、自然收尾的最终版本。"
    "输出必须严格使用以下纯文本格式："
    "第一行：CARD: [卡牌名称]"
    "第二行：留空"
    "第三行开始：完整解读（不少于150字，末尾必须完整句号/问号/感叹号收尾）。"
    "不要输出JSON，不要输出Markdown，不要解释过程。"
)

SENTENCE_ENDINGS = ("。", "！", "？", ".", "!", "?", "”", "」", "』", "）", ")")
CARD_HEADER_PATTERN = re.compile(
    r"^\s*CARD[:：][ \t]*\[?([^\]\r\n]+)\]?[ \t]*\r?\n(?:\r?\n)?",
    flags=re.IGNORECASE,
)
MIN_MEANING_CHARS = 150
MAX_GENERATION_ATTEMPTS = 3
GENERATION_MAX_TOKENS = 4096
STREAM_CHUNK_CHARS = 18

# Match all think-tag variants: <think>, </think>, <|think|>, <|/think|>
THINK_TAG_RE = re.compile(
    r"<\|?think\|?>[\s\S]*?<\|?/?think\|?>",
    flags=re.IGNORECASE,
)
UNCLOSED_THINK_RE = re.compile(
    r"<\|?think\|?>[\s\S]*$",
    flags=re.IGNORECASE,
)


def strip_think_tags(text: str) -> str:
    """Remove all <think>…</think> blocks, including unclosed trailing blocks."""
    cleaned = THINK_TAG_RE.sub("", text)
    cleaned = UNCLOSED_THINK_RE.sub("", cleaned)
    return cleaned.strip()


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
                if item.get("type") in ("thinking", "reasoning"):
                    continue
                text = item.get("text")
                if isinstance(text, str):
                    segments.append(text)
                continue

            item_type = getattr(item, "type", None)
            if item_type in ("thinking", "reasoning"):
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


def build_forced_fallback_meaning(question: str, card_name: str) -> str:
    compact_question = re.sub(r"\s+", " ", question).strip()
    compact_question = compact_question[:60] if compact_question else "你此刻的困惑"
    return (
        f"你抽到「{card_name}」，命运并未沉默，而是在高噪声中给你一条可执行的路径。"
        f"针对“{compact_question}”，先停止追逐外界即时反馈，把注意力拉回你真正可控的三件事："
        "一是明确本周必须完成的最小目标，二是砍掉一切分散精力的伪任务，三是把关键决策写成可验证的条件。"
        "当你不再被情绪和幻象牵引，牌面会从不确定中显露秩序。接下来七天，请用行动而非猜测验证方向，"
        "你会看到局势开始向你倾斜。"
    )


def ensure_non_empty_complete_meaning(question: str, card_name: str, meaning: str) -> str:
    normalized = meaning.strip()
    if meaning_char_count(normalized) < MIN_MEANING_CHARS:
        fallback = build_forced_fallback_meaning(question, card_name)
        normalized = f"{normalized}\n\n{fallback}".strip() if normalized else fallback
    if looks_incomplete(normalized):
        normalized += "。"
    return normalized


def normalize_tarot_output(raw_text: str, question: str) -> str:
    card_name, meaning = parse_card_and_meaning(raw_text)
    if not meaning:
        meaning = strip_card_header(raw_text)
    meaning = ensure_non_empty_complete_meaning(question, card_name, meaning)
    return f"CARD: [{card_name}]\n\n{meaning}"


def _append_no_think(messages: list[dict[str, str]]) -> list[dict[str, str]]:
    """Append /no_think to the last user message so Qwen3 skips internal reasoning."""
    out = [m.copy() for m in messages]
    for m in reversed(out):
        if m.get("role") == "user":
            text = m["content"] or ""
            if "/no_think" not in text:
                m["content"] = text.rstrip() + "\n/no_think"
            break
    return out


def request_model_text(client: OpenAI, messages: list[dict[str, str]]) -> str:
    patched = _append_no_think(messages)
    try:
        response = client.chat.completions.create(
            model=ALIYUN_MODEL,
            stream=False,
            max_tokens=GENERATION_MAX_TOKENS,
            messages=patched,
            extra_body={"enable_thinking": False},
        )
    except Exception:
        # Fallback: retry without extra_body in case API rejects unknown param
        logger.warning("Retrying without extra_body (enable_thinking may not be supported)")
        response = client.chat.completions.create(
            model=ALIYUN_MODEL,
            stream=False,
            max_tokens=GENERATION_MAX_TOKENS,
            messages=patched,
        )
    if not response.choices:
        logger.warning("Model returned no choices")
        return ""
    raw = extract_text(response.choices[0].message.content)
    cleaned = strip_think_tags(raw).replace("\uFEFF", "").strip()
    logger.info("Model raw length=%d, cleaned length=%d, first 200 chars: %s",
                len(raw), len(cleaned), cleaned[:200])
    return cleaned


def build_complete_tarot_text(client: OpenAI, question: str) -> str:
    best_raw = ""
    best_score = -1
    candidate_raw = request_model_text(
        client,
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": question},
        ],
    )

    for attempt in range(MAX_GENERATION_ATTEMPTS):
        if attempt > 0:
            repair_user_prompt = (
                f"用户问题：{question}\n"
                f"当前草稿：\n{candidate_raw or best_raw}\n\n"
                "请修复为完整且连贯的最终版。"
            )
            candidate_raw = request_model_text(
                client,
                [
                    {"role": "system", "content": REPAIR_SYSTEM_PROMPT},
                    {"role": "user", "content": repair_user_prompt},
                ],
            )

        if not candidate_raw:
            continue

        card_name, meaning = parse_card_and_meaning(candidate_raw)
        score = meaning_char_count(meaning)
        if is_meaning_complete(meaning):
            return normalize_tarot_output(candidate_raw, question)

        if score > best_score:
            best_score = score
            best_raw = f"CARD: [{card_name}]\n\n{meaning}" if meaning else f"CARD: [{card_name}]\n\n"

    fallback = normalize_tarot_output(best_raw or candidate_raw or "CARD: [未知卡牌]\n\n", question)
    fallback_card, fallback_meaning = parse_card_and_meaning(fallback)
    fallback_meaning = ensure_non_empty_complete_meaning(question, fallback_card, fallback_meaning)
    return f"CARD: [{fallback_card}]\n\n{fallback_meaning}"


def iter_text_chunks(text: str):
    for index in range(0, len(text), STREAM_CHUNK_CHARS):
        yield text[index : index + STREAM_CHUNK_CHARS]

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
        final_text = build_complete_tarot_text(client, question)
    except Exception as exc:
        logger.error("Model call failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=502, detail=f"调用大模型失败: {exc}") from exc

    # Final safety: strip any residual think tags from the outbound text
    final_text = strip_think_tags(final_text)
    logger.info("Final output length=%d, first 300 chars: %s", len(final_text), final_text[:300])

    return StreamingResponse(iter_text_chunks(final_text), media_type="text/plain; charset=utf-8")
