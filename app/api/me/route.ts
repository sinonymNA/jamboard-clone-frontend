import { prisma } from "@/lib/prisma";
import { getCurrentUserId } from "@/lib/auth";
import { getCurrentSeason, countAttemptsThisPeriod } from "@/lib/season";

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

  const currentSeason = await getCurrentSeason();
  const attemptsUsedThisPeriod = await countAttemptsThisPeriod(user.id, currentSeason?.id ?? null);

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
