import { redirect } from "next/navigation";
import { getCurrentUserId } from "@/lib/auth";
import { prisma } from "@/lib/prisma";
import { getCurrentSeason, countAttemptsThisPeriod } from "@/lib/season";
import { getCurrentTier } from "@/lib/tier";

export const dynamic = "force-dynamic";

export default async function DashboardPage() {
  const userId = await getCurrentUserId();
  if (!userId) redirect("/login");

  const user = await prisma.user.findUnique({ where: { id: userId }, include: { entitlement: true } });
  if (!user) redirect("/login");

  const [currentTier, currentSeason, totalAttempts, passedAttempts] = await Promise.all([
    getCurrentTier(userId),
    getCurrentSeason(),
    prisma.attempt.count({ where: { userId } }),
    prisma.attempt.count({ where: { userId, passed: true } }),
  ]);
  const attemptsUsedThisPeriod = await countAttemptsThisPeriod(userId, currentSeason?.id ?? null);

  const plan = user.entitlement?.plan ?? "FREE";
  const freeAttemptLimit = user.entitlement?.freeAttemptLimit ?? 3;

  return (
    <main style={{ fontFamily: "system-ui", padding: "4rem 2rem", maxWidth: 480 }}>
      <h1>Dashboard</h1>

      <section style={{ border: "1px solid #ccc", borderRadius: 8, padding: "1rem", marginBottom: "1.5rem" }}>
        <h2>Current rank</h2>
        <p>{currentTier ? currentTier.tier.name : "Unranked — pass a Combine to earn your first tier"}</p>
      </section>

      <section style={{ border: "1px solid #ccc", borderRadius: 8, padding: "1rem", marginBottom: "1.5rem" }}>
        <h2>Attempts</h2>
        <p>Total Combine attempts: {totalAttempts}</p>
        <p>Combines passed: {passedAttempts}</p>
        {plan === "FREE" && (
          <p>
            Attempts used this season: {attemptsUsedThisPeriod} / {freeAttemptLimit}
          </p>
        )}
      </section>

      {plan === "FREE" && (
        <p>
          Upgrade to a paid plan for unlimited attempts and a full performance dashboard.
        </p>
      )}
    </main>
  );
}
