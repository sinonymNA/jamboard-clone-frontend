"use client";

import { useState } from "react";

export default function StartAttemptButton({ combineId }: { combineId: string }) {
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
    setStatus("done");
    if (!res.ok) {
      setMessage(body.error ?? "could not start attempt");
      return;
    }
    setMessage(`Attempt started (id: ${body.attempt.id}). Voice roleplay isn't wired up yet.`);
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
