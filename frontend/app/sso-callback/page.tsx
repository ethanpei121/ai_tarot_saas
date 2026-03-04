"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

export default function SSOCallbackPage() {
  const router = useRouter();

  useEffect(() => {
    router.replace("/");
  }, [router]);

  return (
    <main className="flex min-h-screen items-center justify-center bg-black text-sm text-cyan-100">
      认证方式已升级，正在返回首页...
    </main>
  );
}
