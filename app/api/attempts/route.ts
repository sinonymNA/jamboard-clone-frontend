import { prisma } from "@/lib/prisma";
import { getCurrentUserId } from "@/lib/auth";
import { getCurrentSeason, countAttemptsThisPeriod } from "@/lib/season";

export async function POST(request: Request) {
  const userId = await getCurrentUserId();
  if (!userId) {
    return Response.json({ error: "not authenticated" }, { status: 401 });
  }

  const body = await request.json().catch(() => null);
  const combineId = typeof body?.combineId === "string" ? body.combineId : "";
  if (!combineId) {
    return Response.json({ error: "combineId is required" }, { status: 400 });
  }

  const combine = await prisma.combine.findUnique({ where: { id: combineId } });
  if (!combine || !combine.isActive) {
    return Response.json({ error: "combine not found" }, { status: 404 });
  }

  const entitlement = await prisma.entitlement.findUnique({ where: { userId } });
  const plan = entitlement?.plan ?? "FREE";
  const currentSeason = await getCurrentSeason();

  if (plan === "FREE") {
    const limit = entitlement?.freeAttemptLimit ?? 3;
    const used = await countAttemptsThisPeriod(userId, currentSeason?.id ?? null);
    if (used >= limit) {
      return Response.json(
        {
          error: "free attempt limit reached for this period",
          attemptsUsedThisPeriod: used,
          freeAttemptLimit: limit,
        },
        { status: 403 }
      );
    }
  }

  const attempt = await prisma.attempt.create({
    data: {
      userId,
      combineId: combine.id,
      seasonId: currentSeason?.id ?? null,
      status: "IN_PROGRESS",
    },
  });

  return Response.json({ attempt });
}
