import { prisma } from "@/lib/prisma";

export async function awardTierIfEarned(attemptId: string) {
  const attempt = await prisma.attempt.findUnique({
    where: { id: attemptId },
    include: { tierHistoryEvent: true },
  });
  if (!attempt || !attempt.passed || attempt.cumulativeScore === null) return null;
  if (attempt.tierHistoryEvent) return attempt.tierHistoryEvent;

  const earnedTier = await prisma.tier.findFirst({
    where: { passThreshold: { lte: attempt.cumulativeScore } },
    orderBy: { rankOrder: "desc" },
  });
  if (!earnedTier) return null;

  return prisma.tierHistory.create({
    data: {
      userId: attempt.userId,
      tierId: earnedTier.id,
      seasonId: attempt.seasonId,
      attemptId: attempt.id,
    },
  });
}
