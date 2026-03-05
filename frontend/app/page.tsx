"use client";

import {
  Show,
  SignInButton,
  UserButton,
  useAuth,
} from "@clerk/nextjs";
import PaymentModal from "@/components/PaymentModal";
import { type ReactNode, useCallback, useRef, useState } from "react";

/** Characters revealed per tick in the typewriter animation. */
const TYPEWRITER_CHARS_PER_TICK = 2;
/** Interval (ms) between typewriter ticks. */
const TYPEWRITER_INTERVAL_MS = 30;

function SignedIn({ children }: { children: ReactNode }) {
  return <Show when="signed-in">{children}</Show>;
}

function SignedOut({ children }: { children: ReactNode }) {
  return <Show when="signed-out">{children}</Show>;
}

export default function Page() {
  const { userId } = useAuth();
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [cardName, setCardName] = useState("");
  const [meaning, setMeaning] = useState("");
  const [error, setError] = useState("");
  const [showPaymentModal, setShowPaymentModal] = useState(false);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  /** Stop any running typewriter animation. */
  const stopTypewriter = useCallback(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  /** Animate `fullText` character-by-character into the meaning state. */
  const startTypewriter = useCallback(
    (fullText: string) => {
      stopTypewriter();
      let cursor = 0;
      setMeaning("");
      timerRef.current = setInterval(() => {
        cursor += TYPEWRITER_CHARS_PER_TICK;
        if (cursor >= fullText.length) {
          setMeaning(fullText);
          stopTypewriter();
        } else {
          setMeaning(fullText.slice(0, cursor));
        }
      }, TYPEWRITER_INTERVAL_MS);
    },
    [stopTypewriter],
  );

  const handleDrawCard = async () => {
    if (!userId) {
      alert("请先点击右上角登录，获取你的专属星盘");
      return;
    }

    const trimmedQuestion = question.trim();
    if (!trimmedQuestion) {
      alert("请先写下你的困惑");
      return;
    }

    stopTypewriter();
    setLoading(true);
    setError("");
    setCardName("");
    setMeaning("");
    setShowPaymentModal(false);

    try {
      const response = await fetch(
        "https://ai-tarot-saas.onrender.com/draw_card",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            question: trimmedQuestion,
            user_id: userId,
          }),
        },
      );

      /* ---------- 403: quota exhausted ---------- */
      if (response.status === 403) {
        setShowPaymentModal(true);
        let detail = "当前额度不足，请完成支付后继续占卜。";
        try {
          const body = await response.json();
          if (body?.detail) detail = body.detail;
        } catch {
          /* response was not JSON – use default */
        }
        setError(detail);
        return;
      }

      if (!response.ok) {
        let detail = `Request failed: ${response.status}`;
        try {
          const body = await response.json();
          if (body?.detail) detail = body.detail;
        } catch {
          /* ignore */
        }
        throw new Error(detail);
      }

      /* ---------- 200: JSON { card_name, meaning } ---------- */
      const data = await response.json();
      const name: string = data.card_name || "未知卡牌";
      const text: string = data.meaning || "";

      setCardName(name);

      if (text) {
        startTypewriter(text);
      } else {
        setMeaning("命运信号解析失败，请稍后重试。");
      }
    } catch {
      setError("星图信号短暂失联，请确认后端已启动后再试。");
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="relative min-h-screen overflow-hidden bg-gradient-to-b from-gray-900 via-black to-purple-900 px-4 py-10 text-purple-100 md:px-8">
      <div className="pointer-events-none absolute -left-20 top-16 h-64 w-64 rounded-full bg-fuchsia-500/20 blur-3xl" />
      <div className="pointer-events-none absolute -right-20 bottom-10 h-72 w-72 rounded-full bg-amber-400/15 blur-3xl" />

      <div className="absolute right-4 top-4 z-20 md:right-8 md:top-6">
        <SignedOut>
          <div className="rounded-2xl border border-cyan-300/40 bg-black/55 p-1.5 shadow-[0_10px_35px_rgba(0,0,0,0.45)] backdrop-blur-xl">
            <SignInButton mode="modal">
              <button
                type="button"
                className="inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-cyan-300 via-blue-400 to-indigo-400 px-5 py-2.5 text-sm font-semibold text-black transition hover:brightness-110"
              >
                <span className="h-2 w-2 rounded-full bg-emerald-500" />
                登录 / 注册
              </button>
            </SignInButton>
          </div>
        </SignedOut>

        <SignedIn>
          <div className="flex items-center gap-3 rounded-2xl border border-cyan-300/40 bg-black/60 px-3 py-2 shadow-[0_10px_35px_rgba(0,0,0,0.45)] backdrop-blur-xl">
            <span className="text-xs font-medium text-cyan-100">已连接星盘</span>
            <UserButton
              appearance={{
                elements: {
                  avatarBox:
                    "h-10 w-10 ring-2 ring-cyan-200/80 shadow-[0_0_18px_rgba(103,232,249,0.45)]",
                },
              }}
            />
          </div>
        </SignedIn>
      </div>

      <div className="mx-auto flex min-h-[90vh] w-full max-w-4xl items-center justify-center">
        <section className="w-full rounded-3xl border border-purple-300/25 bg-black/45 p-6 shadow-[0_0_60px_rgba(168,85,247,0.25)] backdrop-blur-xl md:p-10">
          <h1 className="text-center text-3xl font-black leading-tight text-yellow-300 [text-shadow:0_0_24px_rgba(250,204,21,0.55)] md:text-5xl">
            🔮 赛博解忧室 / AI 塔罗占卜
          </h1>

          <p className="mx-auto mt-4 max-w-2xl text-center text-sm text-purple-200 md:text-lg">
            倾诉你的迷茫，大模型为你抽取命运的指引。
          </p>

          <div className="mt-8">
            <label
              htmlFor="question"
              className="mb-2 block text-sm text-purple-300"
            >
              你的问题
            </label>
            <textarea
              id="question"
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              placeholder="请在此写下你心中的困惑（如：我下个月能拿到心仪的Offer吗？）"
              className="h-44 w-full resize-none rounded-2xl border border-purple-300/35 bg-black/50 p-4 text-base leading-relaxed text-purple-100 outline-none transition focus:border-yellow-300/70 focus:ring-2 focus:ring-yellow-300/30"
            />
          </div>

          <div className="mt-6 flex justify-center">
            <button
              type="button"
              onClick={handleDrawCard}
              disabled={loading}
              className="rounded-xl bg-gradient-to-r from-violet-600 via-fuchsia-600 to-amber-500 px-8 py-3 text-base font-semibold text-white shadow-[0_0_26px_rgba(217,70,239,0.45)] transition hover:from-violet-500 hover:via-fuchsia-500 hover:to-amber-400 disabled:cursor-not-allowed disabled:opacity-70"
            >
              {loading ? "命运之轮转动中..." : "✨ 抽取命运之牌"}
            </button>
          </div>

          {error && (
            <div className="mt-6 rounded-xl border border-red-400/30 bg-red-950/30 p-4 text-center text-red-200">
              {error}
            </div>
          )}

          {(loading || cardName || meaning) && (
            <div className="mt-8 rounded-2xl border border-yellow-300/35 bg-gradient-to-b from-purple-900/45 to-black/70 p-6 shadow-[0_0_30px_rgba(250,204,21,0.22)]">
              <p className="text-center text-xs uppercase tracking-[0.25em] text-purple-300/90">
                Arcane Transmission
              </p>
              <h2 className="mt-2 text-center text-3xl font-bold text-yellow-300 md:text-4xl">
                {cardName || "正在抽牌..."}
              </h2>
              <p className="mt-5 whitespace-pre-wrap text-center text-base leading-8 text-purple-100/95 md:text-lg">
                {meaning || (loading ? "命运信号接入中..." : "")}
              </p>
            </div>
          )}
        </section>
      </div>

      <PaymentModal
        isOpen={showPaymentModal}
        onClose={() => setShowPaymentModal(false)}
      />
    </main>
  );
}
