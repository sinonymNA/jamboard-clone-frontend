import { prisma } from "@/lib/prisma";
import { getCurrentUserId } from "@/lib/auth";

export async function GET() {
  const userId = await getCurrentUserId();
  if (!userId) {
    return Response.json({ error: "not authenticated" }, { status: 401 });
  }

  const user = await prisma.user.findUnique({
    where: { id: userId },
    include: { entitlement: true },
  });
  if (!user) {
    return Response.json({ error: "not authenticated" }, { status: 401 });
  }

  const currentSeason = await prisma.season.findFirst({ where: { isActive: true } });

  const attemptsUsedThisPeriod = currentSeason
    ? await prisma.attempt.count({
        where: { userId: user.id, seasonId: currentSeason.id },
      })
    : 0;

  return Response.json({
    id: user.id,
    email: user.email,
    displayName: user.displayName,
    plan: user.entitlement?.plan ?? "FREE",
    freeAttemptLimit: user.entitlement?.freeAttemptLimit ?? 3,
    attemptsUsedThisPeriod,
    currentSeason: currentSeason ? { id: currentSeason.id, name: currentSeason.name } : null,
  });
}
