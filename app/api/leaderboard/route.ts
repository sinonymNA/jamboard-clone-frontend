import { prisma } from "@/lib/prisma";
import { getLeaderboard } from "@/lib/leaderboard";

export async function GET(request: Request) {
  const url = new URL(request.url);
  const seasonIdParam = url.searchParams.get("seasonId");

  let seasonId: string | null;
  if (seasonIdParam === "none") {
    seasonId = null;
  } else if (seasonIdParam) {
    seasonId = seasonIdParam;
  } else {
    const currentSeason = await prisma.season.findFirst({ where: { isActive: true } });
    seasonId = currentSeason?.id ?? null;
  }

  const rows = await getLeaderboard(seasonId);
  return Response.json({ seasonId, rows });
}
