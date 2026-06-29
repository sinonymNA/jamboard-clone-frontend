"use client";

import { useRef, useState } from "react";

type TranscriptEntry = { role: "user" | "assistant"; text: string; timestamp: string };

type CallState = "idle" | "connecting" | "active" | "ended" | "error";

export type AttemptSnapshot = {
  status: "IN_PROGRESS" | "COMPLETED" | "ABANDONED";
  cumulativeScore: number | null;
  passed: boolean | null;
};

export default function VoiceSession({
  attemptId,
  scenarioName,
  onEnded,
}: {
  attemptId: string;
  scenarioName: string;
  onEnded?: (result: { attempt: AttemptSnapshot | null; gradingError: string | null }) => void;
}) {
  const [state, setState] = useState<CallState>("idle");
  const [error, setError] = useState<string | null>(null);
  const [transcript, setTranscript] = useState<TranscriptEntry[]>([]);
  const [gradingError, setGradingError] = useState<string | null>(null);

  const pcRef = useRef<RTCPeerConnection | null>(null);
  const dcRef = useRef<RTCDataChannel | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const scenarioAttemptIdRef = useRef<string | null>(null);
  const pendingDeltaRef = useRef<{ role: "user" | "assistant"; text: string } | null>(null);

  function appendTranscript(role: "user" | "assistant", text: string) {
    if (!text) return;
    setTranscript((prev) => [...prev, { role, text, timestamp: new Date().toISOString() }]);
  }

  function handleDataChannelMessage(raw: string) {
    let event: { type?: string; transcript?: string; delta?: string };
    try {
      event = JSON.parse(raw);
    } catch {
      return;
    }
    const type = event.type ?? "";

    // OpenAI Realtime transcript event names have shifted across API
    // versions, so we match a few plausible variants defensively.
    if (type === "conversation.item.input_audio_transcription.delta") {
      pendingDeltaRef.current ??= { role: "user", text: "" };
      pendingDeltaRef.current.text += event.delta ?? "";
    } else if (type === "conversation.item.input_audio_transcription.completed") {
      appendTranscript("user", event.transcript ?? pendingDeltaRef.current?.text ?? "");
      pendingDeltaRef.current = null;
    } else if (
      type === "response.output_audio_transcript.delta" ||
      type === "response.audio_transcript.delta"
    ) {
      pendingDeltaRef.current ??= { role: "assistant", text: "" };
      pendingDeltaRef.current.text += event.delta ?? "";
    } else if (
      type === "response.output_audio_transcript.done" ||
      type === "response.audio_transcript.done"
    ) {
      appendTranscript("assistant", event.transcript ?? pendingDeltaRef.current?.text ?? "");
      pendingDeltaRef.current = null;
    }
  }

  async function startCall() {
    setState("connecting");
    setError(null);

    const sessionRes = await fetch("/api/realtime/session", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ attemptId }),
    });
    const session = await sessionRes.json().catch(() => ({}));
    if (!sessionRes.ok) {
      setError(session.error ?? "could not start voice session");
      setState("error");
      return;
    }
    scenarioAttemptIdRef.current = session.scenarioAttemptId;

    const pc = new RTCPeerConnection();
    pcRef.current = pc;

    pc.ontrack = (event) => {
      if (audioRef.current) audioRef.current.srcObject = event.streams[0];
    };

    const dc = pc.createDataChannel("oai-events");
    dc.onmessage = (event) => handleDataChannelMessage(event.data);
    dcRef.current = dc;

    try {
      const mic = await navigator.mediaDevices.getUserMedia({ audio: true });
      mic.getTracks().forEach((track) => pc.addTrack(track, mic));
    } catch {
      setError("microphone access is required for the voice roleplay");
      setState("error");
      return;
    }

    const offer = await pc.createOffer();
    await pc.setLocalDescription(offer);

    const callRes = await fetch("https://api.openai.com/v1/realtime/calls", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${session.clientSecret}`,
        "Content-Type": "application/sdp",
      },
      body: offer.sdp,
    });
    if (!callRes.ok) {
      setError("could not connect to the voice service");
      setState("error");
      return;
    }
    const answerSdp = await callRes.text();
    await pc.setRemoteDescription({ type: "answer", sdp: answerSdp });

    setState("active");
  }

  async function endCall() {
    pcRef.current?.getSenders().forEach((sender) => sender.track?.stop());
    pcRef.current?.close();
    pcRef.current = null;

    const scenarioAttemptId = scenarioAttemptIdRef.current;
    let attempt: AttemptSnapshot | null = null;
    let resultGradingError: string | null = null;
    if (scenarioAttemptId) {
      const res = await fetch(`/api/scenario-attempts/${scenarioAttemptId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ transcript }),
      });
      const body = await res.json().catch(() => ({}));
      attempt = body.attempt ?? null;
      resultGradingError = body.gradingError ?? null;
      setGradingError(resultGradingError);
    }
    setState("ended");
    onEnded?.({ attempt, gradingError: resultGradingError });
  }

  return (
    <div>
      <h2>{scenarioName}</h2>
      <audio ref={audioRef} autoPlay />
      {state === "idle" && <button onClick={startCall}>Start voice roleplay</button>}
      {state === "connecting" && <p>Connecting...</p>}
      {state === "active" && <button onClick={endCall}>End call</button>}
      {state === "ended" && (
        <p>{gradingError ? `Call ended. Transcript saved — ${gradingError}` : "Call ended. Transcript saved and graded."}</p>
      )}
      {state === "error" && (
        <div>
          <p>{error}</p>
          <button onClick={startCall}>Retry</button>
        </div>
      )}
      <ul style={{ listStyle: "none", padding: 0, marginTop: "1.5rem", display: "flex", flexDirection: "column", gap: "0.5rem" }}>
        {transcript.map((entry, i) => (
          <li key={i}>
            <strong>{entry.role}:</strong> {entry.text}
          </li>
        ))}
      </ul>
    </div>
  );
}
