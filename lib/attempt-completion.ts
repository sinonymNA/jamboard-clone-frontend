import { prisma } from "@/lib/prisma";
import { awardTierIfEarned } from "@/lib/tier";

export async function maybeCompleteAttempt(attemptId: string) {
  const attempt = await prisma.attempt.findUnique({
    where: { id: attemptId },
    include: {
      combine: { include: { combineScenarios: true } },
      scenarioAttempts: true,
    },
  });
  if (!attempt || attempt.status !== "IN_PROGRESS") return null;

  const totalScenarios = attempt.combine.combineScenarios.length;
  const gradedAttempts = attempt.scenarioAttempts.filter((sa) => sa.rollupScore !== null);
  if (gradedAttempts.length < totalScenarios) return null;

  const cumulativeScore = gradedAttempts.reduce((sum, sa) => sum + (sa.rollupScore ?? 0), 0);
  const floorBreachedAny = gradedAttempts.some((sa) => sa.floorBreached === true);
  const passed = !floorBreachedAny && cumulativeScore >= attempt.combine.cumulativeTarget;

  const completed = await prisma.attempt.update({
    where: { id: attemptId },
    data: { status: "COMPLETED", cumulativeScore, passed, completedAt: new Date() },
  });

  if (passed) {
    await awardTierIfEarned(attemptId);
  }

  return completed;
}
