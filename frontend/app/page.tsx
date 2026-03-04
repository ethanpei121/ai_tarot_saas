"use client";

import { GuardProvider, type User, useGuard } from "@authing/guard-react18";
import { useEffect, useMemo, useRef, useState } from "react";

type ParsedHeader = {
  cardName: string;
  consumed: number;
};

type GuardWithUser = ReturnType<typeof useGuard> & {
  user?: User | null;
  show?: () => void;
  hide?: () => void;
  startRegister?: () => void;
  changeView?: (view: string) => Promise<void> | void;
};

const GUARD_MULTIPLE_ACCOUNT_KEY = "__authing__multiple_accounts";
const GUARD_HISTORY_PATCH_MARK = "__guardHistoryCompatPatched";

type HistoryWithCompatPatch = History & {
  [GUARD_HISTORY_PATCH_MARK]?: boolean;
};

function normalizeNextHistoryState(state: unknown) {
  if (state === null || typeof state === "object") {
    return state;
  }

  return { __guardModule: String(state) };
}

function installGuardNextHistoryCompatPatch() {
  if (typeof window === "undefined") {
    return;
  }

  const historyWithPatch = window.history as HistoryWithCompatPatch;
  if (historyWithPatch[GUARD_HISTORY_PATCH_MARK]) {
    return;
  }

  const originalPushState = window.history.pushState.bind(window.history);
  const originalReplaceState = window.history.replaceState.bind(window.history);

  window.history.pushState = ((state, unused, url) => {
    return originalPushState(normalizeNextHistoryState(state), unused, url);
  }) as History["pushState"];

  window.history.replaceState = ((state, unused, url) => {
    return originalReplaceState(normalizeNextHistoryState(state), unused, url);
  }) as History["replaceState"];

  historyWithPatch[GUARD_HISTORY_PATCH_MARK] = true;
}

function clearGuardMultipleAccountCache() {
  if (typeof window === "undefined") {
    return;
  }

  try {
    window.localStorage.removeItem(GUARD_MULTIPLE_ACCOUNT_KEY);
  } catch {
    // Ignore storage access errors.
  }
}

function parseCardHeader(buffer: string): ParsedHeader | null {
  const strictMatch = buffer.match(/^CARD[:：]\s*\[?([^\]\r\n]+)\]?\s*\r?\n\r?\n/i);
  if (strictMatch) {
    return {
      cardName: strictMatch[1]?.trim() || "未知卡牌",
      consumed: strictMatch[0].length,
    };
  }

  const looseMatch = buffer.match(/^CARD[:：]\s*\[?([^\]\r\n]+)\]?\s*\r?\n/i);
  if (!looseMatch) {
    return null;
  }

  const rest = buffer.slice(looseMatch[0].length);
  if (!rest || /^[\r\n]+$/.test(rest)) {
    return null;
  }

  return {
    cardName: looseMatch[1]?.trim() || "未知卡牌",
    consumed: looseMatch[0].length,
  };
}

function TarotPageContent() {
  const guard = useGuard() as GuardWithUser;
  const { start, user, logout, show, startRegister, changeView } = guard;

  const [currentUser, setCurrentUser] = useState<User | null>(user ?? null);
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [cardName, setCardName] = useState("");
  const [meaning, setMeaning] = useState("");
  const [error, setError] = useState("");
  const hasBoundGuardEventsRef = useRef(false);

  useEffect(() => {
    installGuardNextHistoryCompatPatch();
    clearGuardMultipleAccountCache();
  }, []);

  useEffect(() => {
    let active = true;

    guard
      .trackSession()
      .then((sessionUser) => {
        if (!active) {
          return;
        }

        setCurrentUser(sessionUser);

        if (sessionUser) {
          guard.hide?.call(guard);
        }
      })
      .catch(() => {
        if (active) {
          setCurrentUser(guard.user ?? null);
        }
      });

    if (!hasBoundGuardEventsRef.current) {
      hasBoundGuardEventsRef.current = true;
      guard.on("login", (loggedInUser) => {
        setCurrentUser(loggedInUser);
        guard.hide?.call(guard);
      });
    }

    return () => {
      active = false;
    };
  }, [guard]);

  const displayName = useMemo(() => {
    if (!currentUser) {
      return "";
    }

    return (
      currentUser.nickname ||
      currentUser.username ||
      currentUser.name ||
      currentUser.email ||
      "已登录用户"
    );
  }, [currentUser]);

  const avatarInitial = displayName ? displayName.slice(0, 1).toUpperCase() : "我";

  const handleAuthingLogin = () => {
    const scrollTop = window.scrollY;
    clearGuardMultipleAccountCache();

    if (typeof show === "function") {
      show.call(guard);
      window.setTimeout(() => {
        window.scrollTo({ top: scrollTop, behavior: "auto" });
      }, 0);
      return;
    }

    void start
      .call(guard)
      .then((loggedInUser) => {
        setCurrentUser(loggedInUser);
        guard.hide?.call(guard);
      })
      .catch(() => {
        alert("登录暂不可用，请稍后重试。");
      });
  };

  const handleAuthingRegister = () => {
    const scrollTop = window.scrollY;
    clearGuardMultipleAccountCache();

    if (typeof show === "function") {
      show.call(guard);
      if (typeof changeView === "function") {
        void Promise.resolve(changeView.call(guard, "register")).catch(() => {
          if (typeof startRegister === "function") {
            startRegister.call(guard);
          }
        });
      } else if (typeof startRegister === "function") {
        startRegister.call(guard);
      }
      window.setTimeout(() => {
        window.scrollTo({ top: scrollTop, behavior: "auto" });
      }, 0);
      return;
    }

    if (typeof startRegister === "function") {
      startRegister.call(guard);
      return;
    }

    alert("注册模块暂不可用，请稍后重试。");
  };

  const handleLogout = async () => {
    try {
      await logout.call(guard);
      setCurrentUser(null);
    } catch {
      alert("退出失败，请稍后重试。");
    }
  };

  const handleDrawCard = async () => {
    if (!currentUser?.id) {
      alert("请先点击右上角登录");
      return;
    }

    const trimmedQuestion = question.trim();
    if (!trimmedQuestion) {
      alert("请先写下你的困惑");
      return;
    }

    setLoading(true);
    setError("");
    setCardName("");
    setMeaning("");

    try {
      const response = await fetch("https://ai-tarot-saas.onrender.com/draw_card", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          question: trimmedQuestion,
          user_id: currentUser.id,
        }),
      });

      if (!response.ok) {
        throw new Error(`Request failed: ${response.status}`);
      }

      if (!response.body) {
        throw new Error("Streaming not supported in this browser");
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder("utf-8");

      let buffer = "";
      let cardParsed = false;

      const processBuffer = () => {
        if (!cardParsed) {
          const parsedHeader = parseCardHeader(buffer);
          if (!parsedHeader) {
            return;
          }

          setCardName(parsedHeader.cardName);
          buffer = buffer.slice(parsedHeader.consumed);
          cardParsed = true;
        }

        if (cardParsed && buffer) {
          setMeaning((prev) => prev + buffer);
          buffer = "";
        }
      };

      while (true) {
        const { done, value } = await reader.read();
        if (value) {
          buffer += decoder.decode(value, { stream: !done });
          processBuffer();
        }
        if (done) {
          break;
        }
      }

      const trailing = decoder.decode();
      if (trailing) {
        buffer += trailing;
        processBuffer();
      }

      if (!cardParsed && buffer.trim()) {
        setCardName("未知卡牌");
        setMeaning((prev) => prev + buffer.replace(/^\uFEFF/, "").trim());
      } else if (buffer) {
        setMeaning((prev) => prev + buffer);
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
        {!currentUser ? (
          <div className="rounded-2xl border border-cyan-300/40 bg-black/55 p-1.5 shadow-[0_10px_35px_rgba(0,0,0,0.45)] backdrop-blur-xl">
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={handleAuthingLogin}
                className="inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-cyan-300 via-blue-400 to-indigo-400 px-4 py-2 text-sm font-semibold text-black transition hover:brightness-110"
              >
                <span className="h-2 w-2 rounded-full bg-emerald-500" />
                登录
              </button>
              <button
                type="button"
                onClick={handleAuthingRegister}
                className="inline-flex items-center gap-2 rounded-xl border border-amber-300/60 bg-amber-300/90 px-4 py-2 text-sm font-semibold text-black transition hover:brightness-110"
              >
                注册
              </button>
            </div>
            <p className="mt-1 text-center text-[11px] text-cyan-100/80">
              仅支持手机号登录/注册（验证码 + 手机密码）
            </p>
          </div>
        ) : (
          <div className="flex items-center gap-3 rounded-2xl border border-cyan-300/40 bg-black/60 px-3 py-2 shadow-[0_10px_35px_rgba(0,0,0,0.45)] backdrop-blur-xl">
            {currentUser.photo ? (
              <span
                className="h-8 w-8 rounded-full border border-cyan-200/80 bg-cover bg-center"
                style={{ backgroundImage: `url(${currentUser.photo})` }}
                aria-label={displayName}
              />
            ) : (
              <span className="flex h-8 w-8 items-center justify-center rounded-full border border-cyan-200/80 bg-cyan-500/20 text-xs font-bold text-cyan-100">
                {avatarInitial}
              </span>
            )}

            <span
              className="max-w-[120px] truncate text-xs font-medium text-cyan-100"
              title={displayName}
            >
              {displayName}
            </span>

            <button
              type="button"
              onClick={handleLogout}
              className="rounded-xl border border-red-300/40 bg-red-500/20 px-3 py-1 text-xs font-semibold text-red-100 transition hover:bg-red-500/35"
            >
              退出
            </button>
          </div>
        )}
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
            <label htmlFor="question" className="mb-2 block text-sm text-purple-300">
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
    </main>
  );
}

export default function Page() {
  const appId = process.env.NEXT_PUBLIC_AUTHING_APP_ID;
  const appHost = process.env.NEXT_PUBLIC_AUTHING_APP_HOST;
  const guardConfig = {
    disableRegister: false,
    autoRegister: false,
    disableResetPwd: false,
    // Keep both naming styles for Guard config compatibility.
    loginMethods: ["phone-code", "password"],
    loginMethodList: ["phone-code", "password"],
    defaultLoginMethod: "phone-code",
    loginMethod: "phone-code",
    passwordLoginMethods: ["phone-password"],
    registerMethods: ["phone"],
    registerMethodList: ["phone"],
    defaultRegisterMethod: "phone",
    registerMethod: "phone",
  };

  if (!appId || !appHost) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-black px-6 text-purple-100">
        <div className="max-w-xl rounded-2xl border border-red-400/40 bg-red-950/35 p-6 text-center">
          <h1 className="text-xl font-bold text-red-200">Authing 配置缺失</h1>
          <p className="mt-3 text-sm text-red-100/90">
            请在 frontend/.env.local 中设置 NEXT_PUBLIC_AUTHING_APP_ID 与
            NEXT_PUBLIC_AUTHING_APP_HOST。
          </p>
        </div>
      </main>
    );
  }

  return (
    <GuardProvider
      appId={appId}
      host={appHost}
      align="center"
      mode="modal"
      config={guardConfig}
    >
      <TarotPageContent />
    </GuardProvider>
  );
}


