import { prisma } from "@/lib/prisma";

export function getCurrentSeason() {
  return prisma.season.findFirst({ where: { isActive: true } });
}

export function countAttemptsThisPeriod(userId: string, seasonId: string | null) {
  // seasonId: null filters for "IS NULL" (attempts taken while no season was active),
  // not "skip this filter" -- the two are different in Prisma's where input.
  return prisma.attempt.count({ where: { userId, seasonId } });
}
