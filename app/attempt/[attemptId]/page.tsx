import { redirect } from "next/navigation";
import { prisma } from "@/lib/prisma";
import { getCurrentUserId } from "@/lib/auth";
import AttemptFlow from "./attempt-flow";

export const dynamic = "force-dynamic";

export default async function AttemptPage({
  params,
}: PageProps<"/attempt/[attemptId]">) {
  const { attemptId } = await params;
  const userId = await getCurrentUserId();
  if (!userId) redirect("/login");

  const attempt = await prisma.attempt.findUnique({
    where: { id: attemptId },
    include: { combine: true, scenarioAttempts: true, tierHistoryEvent: { include: { tier: true } } },
  });
  if (!attempt || attempt.userId !== userId) redirect("/combines");

  const combineScenarios = await prisma.combineScenario.findMany({
    where: { combineId: attempt.combineId },
    orderBy: { sortOrder: "asc" },
    include: { scenario: true },
  });
  if (combineScenarios.length === 0) redirect("/combines");

  const scenarios = combineScenarios.map((cs) => {
    const scenarioAttempt = attempt.scenarioAttempts.find((sa) => sa.combineScenarioId === cs.id);
    return { name: cs.scenario.name, completed: Boolean(scenarioAttempt?.completedAt) };
  });

  return (
    <main style={{ fontFamily: "system-ui", padding: "4rem 2rem", maxWidth: 720 }}>
      <h1>Attempt</h1>
      <AttemptFlow
        attemptId={attempt.id}
        combineName={attempt.combine.name}
        cumulativeTarget={attempt.combine.cumulativeTarget}
        scenarios={scenarios}
        initialAttempt={{
          status: attempt.status,
          cumulativeScore: attempt.cumulativeScore,
          passed: attempt.passed,
          tierHistoryEvent: attempt.tierHistoryEvent,
        }}
      />
    </main>
  );
}
