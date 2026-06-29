import { prisma } from "@/lib/prisma";

export type LeaderboardRow = {
  userId: string;
  displayName: string;
  tierName: string;
  rankOrder: number;
  score: number;
  achievedAt: Date;
};

// Derived query, not a materialized view: a JOIN LATERAL pulls each user's
// current (non-revoked) tier, and a second LEFT JOIN LATERAL pulls their best
// completed cumulative score within the given season. seasonId may be null
// (matches Attempts taken while no season was active), so the comparison
// below uses IS NOT DISTINCT FROM rather than `=` to handle that case.
export async function getLeaderboard(seasonId: string | null): Promise<LeaderboardRow[]> {
  return prisma.$queryRaw<LeaderboardRow[]>`
    SELECT
      u.id AS "userId",
      u."displayName" AS "displayName",
      t.name AS "tierName",
      t."rankOrder" AS "rankOrder",
      COALESCE(season_stats.best_score, 0)::int AS score,
      th."achievedAt" AS "achievedAt"
    FROM "User" u
    JOIN LATERAL (
      SELECT *
      FROM "TierHistory" th
      WHERE th."userId" = u.id AND th."revokedAt" IS NULL
      ORDER BY th."achievedAt" DESC
      LIMIT 1
    ) th ON true
    JOIN "Tier" t ON t.id = th."tierId"
    LEFT JOIN LATERAL (
      SELECT MAX(a."cumulativeScore") AS best_score
      FROM "Attempt" a
      WHERE a."userId" = u.id
        AND a."seasonId" IS NOT DISTINCT FROM ${seasonId}
        AND a.status = 'COMPLETED'
    ) season_stats ON true
    ORDER BY t."rankOrder" DESC, season_stats.best_score DESC NULLS LAST, th."achievedAt" ASC
  `;
}
