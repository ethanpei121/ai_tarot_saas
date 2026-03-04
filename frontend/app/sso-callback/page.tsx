"use client";

import { Guard } from "@authing/guard-react18";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

const AUTHING_APP_ID = "69a7caba4934b0cc04c4783a";
const AUTHING_APP_HOST = "https://ai-tarot-ethan.authing.cn";

export default function SSOCallbackPage() {
  const router = useRouter();

  useEffect(() => {
    let active = true;

    const redirectUri = `${window.location.origin}/sso-callback`;
    const guard = new Guard({
      appId: AUTHING_APP_ID,
      host: AUTHING_APP_HOST,
      redirectUri,
    });

    void guard
      .handleRedirectCallback()
      .catch(() => {
        // Keep UX predictable even if callback parsing fails.
      })
      .finally(() => {
        if (active) {
          router.replace("/");
        }
      });

    return () => {
      active = false;
    };
  }, [router]);

  return (
    <main className="flex min-h-screen items-center justify-center bg-black text-sm text-cyan-100">
      正在处理登录回调，请稍候...
    </main>
  );
}
