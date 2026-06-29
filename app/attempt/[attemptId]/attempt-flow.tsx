"use client";

import { useState } from "react";
import VoiceSession, { AttemptSnapshot } from "./voice-session";

type ScenarioSummary = { name: string; completed: boolean };

export default function AttemptFlow({
  attemptId,
  combineName,
  cumulativeTarget,
  scenarios,
  initialAttempt,
}: {
  attemptId: string;
  combineName: string;
  cumulativeTarget: number;
  scenarios: ScenarioSummary[];
  initialAttempt: AttemptSnapshot;
}) {
  const [attempt, setAttempt] = useState<AttemptSnapshot>(initialAttempt);
  const [completedCount, setCompletedCount] = useState(scenarios.filter((s) => s.completed).length);
  const [round, setRound] = useState(0);

  function handleEnded(result: { attempt: AttemptSnapshot | null; gradingError: string | null }) {
    if (result.attempt) setAttempt(result.attempt);
    setCompletedCount((c) => c + 1);
    setRound((r) => r + 1);
  }

  if (attempt.status === "COMPLETED") {
    return (
      <div>
        <h2>{attempt.passed ? "Combine passed" : "Combine failed"}</h2>
        <p>
          Cumulative score: {attempt.cumulativeScore} / {cumulativeTarget}
        </p>
        {attempt.tierHistoryEvent && <p>Tier earned: {attempt.tierHistoryEvent.tier.name}</p>}
      </div>
    );
  }

  if (completedCount >= scenarios.length) {
    return (
      <div>
        <p>Grading is still finishing up on the last scenario.</p>
        <button onClick={() => window.location.reload()}>Check again</button>
      </div>
    );
  }

  const current = scenarios[completedCount];

  return (
    <div>
      <p>
        Scenario {completedCount + 1} of {scenarios.length} — {combineName}
      </p>
      <VoiceSession key={round} attemptId={attemptId} scenarioName={current.name} onEnded={handleEnded} />
    </div>
  );
}
