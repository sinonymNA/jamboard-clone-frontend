"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

export default function StartAttemptButton({ combineId }: { combineId: string }) {
  const router = useRouter();
  const [status, setStatus] = useState<"idle" | "loading" | "done">("idle");
  const [message, setMessage] = useState<string | null>(null);

  async function handleClick() {
    setStatus("loading");
    setMessage(null);
    const res = await fetch("/api/attempts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ combineId }),
    });
    const body = await res.json().catch(() => ({}));
    if (!res.ok) {
      setStatus("done");
      setMessage(body.error ?? "could not start attempt");
      return;
    }
    router.push(`/attempt/${body.attempt.id}`);
  }

  return (
    <div>
      <button onClick={handleClick} disabled={status === "loading"}>
        {status === "loading" ? "Starting..." : "Start attempt"}
      </button>
      {message && <p>{message}</p>}
    </div>
  );
}
