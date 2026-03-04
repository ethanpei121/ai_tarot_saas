"use client";

import { useAuth } from "@clerk/nextjs";
import Image from "next/image";
import { useState } from "react";

type PaymentModalProps = {
  isOpen: boolean;
  onClose: () => void;
};

const COPY_FEEDBACK_MS = 1800;

export default function PaymentModal({ isOpen, onClose }: PaymentModalProps) {
  const { userId } = useAuth();
  const [copied, setCopied] = useState(false);

  if (!isOpen) {
    return null;
  }

  const handleClose = () => {
    setCopied(false);
    onClose();
  };

  const handleCopyId = async () => {
    if (!userId) {
      return;
    }

    try {
      await navigator.clipboard.writeText(userId);
      setCopied(true);
      window.setTimeout(() => setCopied(false), COPY_FEEDBACK_MS);
    } catch {
      alert("复制失败，请手动复制下方用户 ID。");
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center px-4 py-6">
      <button
        type="button"
        onClick={handleClose}
        aria-label="关闭支付弹窗遮罩"
        className="absolute inset-0 bg-black/75 backdrop-blur-sm"
      />

      <section className="relative z-10 w-full max-w-lg rounded-3xl border border-amber-300/35 bg-gradient-to-b from-[#0e071a]/95 via-[#12061f]/95 to-[#050307]/95 p-6 text-purple-100 shadow-[0_0_40px_rgba(250,204,21,0.2)] md:p-8">
        <p className="text-center text-xs uppercase tracking-[0.32em] text-amber-200/80">
          Arcane Checkout
        </p>
        <h3 className="mt-3 text-center text-2xl font-extrabold text-amber-300 md:text-3xl">
          【命运的能量需要交汇】
        </h3>

        <p className="mx-auto mt-4 max-w-xl text-center text-sm leading-7 text-purple-100/90 md:text-base">
          您近期的免费命运指引已达上限。扫码添加解忧师微信，支付 9.9 元红包，即可获取
          100 次塔罗占卜额度。
        </p>

        <div className="mt-6 flex justify-center">
          <div className="rounded-2xl border border-amber-200/30 bg-black/35 p-3 shadow-[0_0_24px_rgba(168,85,247,0.3)]">
            <Image
              src="/wechat.png"
              alt="微信支付二维码"
              width={360}
              height={360}
              className="h-auto w-full max-w-[260px] rounded-xl object-cover shadow-[0_0_25px_rgba(0,0,0,0.4)]"
              priority
            />
          </div>
        </div>

        <div className="mt-6 rounded-2xl border border-cyan-300/35 bg-black/45 p-4">
          <p className="text-xs text-cyan-200/80">你的 Clerk 用户 ID</p>
          <p className="mt-2 break-all font-mono text-sm text-cyan-100">
            {userId || "未检测到 userId，请先登录后重试。"}
          </p>
          <p className="mt-2 text-xs text-purple-200/90">
            添加微信后请发送此 ID，便于后台为你充值占卜额度。
          </p>
        </div>

        <div className="mt-5 flex flex-wrap items-center justify-center gap-3">
          <button
            type="button"
            onClick={handleCopyId}
            disabled={!userId}
            className="rounded-xl border border-cyan-200/50 bg-cyan-300/90 px-4 py-2 text-sm font-semibold text-black transition hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-55"
          >
            {copied ? "已复制" : "一键复制 ID"}
          </button>
          <button
            type="button"
            onClick={handleClose}
            className="rounded-xl border border-amber-200/50 bg-amber-300/90 px-4 py-2 text-sm font-semibold text-black transition hover:brightness-110"
          >
            暂时关闭
          </button>
        </div>
      </section>
    </div>
  );
}
