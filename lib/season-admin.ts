import { prisma } from "@/lib/prisma";

export function createSeason(name: string, startsAt: Date, endsAt: Date) {
  if (endsAt <= startsAt) throw new Error("endsAt must be after startsAt");
  return prisma.season.create({ data: { name, startsAt, endsAt, isActive: false } });
}

// Closes whichever season is currently active (if any) and activates the named
// season in one transaction, preserving the "exactly one active season" invariant.
export async function activateSeason(name: string) {
  return prisma.$transaction(async (tx) => {
    const target = await tx.season.findFirst({ where: { name } });
    if (!target) throw new Error(`no season named "${name}"`);

    const currentlyActive = await tx.season.findMany({ where: { isActive: true, NOT: { id: target.id } } });
    const now = new Date();
    for (const season of currentlyActive) {
      // record the actual close time if it's closing early; never push endsAt later than planned
      await tx.season.update({
        where: { id: season.id },
        data: { isActive: false, endsAt: season.endsAt > now ? now : season.endsAt },
      });
    }

    return tx.season.update({ where: { id: target.id }, data: { isActive: true } });
  });
}

// Deactivates the current season without opening a new one.
export async function closeCurrentSeason() {
  const current = await prisma.season.findFirst({ where: { isActive: true } });
  if (!current) return null;
  const now = new Date();
  return prisma.season.update({
    where: { id: current.id },
    data: { isActive: false, endsAt: current.endsAt > now ? now : current.endsAt },
  });
}

export function listSeasons() {
  return prisma.season.findMany({ orderBy: { startsAt: "asc" } });
}
