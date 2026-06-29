import { prisma } from "@/lib/prisma";
import { getLeaderboard } from "@/lib/leaderboard";

export const dynamic = "force-dynamic";

export default async function LeaderboardPage({
  searchParams,
}: {
  searchParams: Promise<{ seasonId?: string }>;
}) {
  const { seasonId: requestedSeasonId } = await searchParams;

  const seasons = await prisma.season.findMany({ orderBy: { startsAt: "desc" } });
  const currentSeason = seasons.find((s) => s.isActive) ?? null;

  const viewingNone = requestedSeasonId === "none";
  const seasonId = viewingNone ? null : requestedSeasonId ?? currentSeason?.id ?? null;
  const selectedSeason = seasons.find((s) => s.id === seasonId) ?? null;

  const rows = await getLeaderboard(seasonId);

  return (
    <main style={{ fontFamily: "system-ui", padding: "4rem 2rem", maxWidth: 720 }}>
      <h1>Leaderboard</h1>

      <nav style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem", marginBottom: "1.5rem" }}>
        {seasons.map((s) => (
          <a
            key={s.id}
            href={`/leaderboard?seasonId=${s.id}`}
            style={{ fontWeight: s.id === seasonId ? "bold" : "normal" }}
          >
            {s.name}
            {s.isActive ? " (current)" : ""}
          </a>
        ))}
        <a href="/leaderboard?seasonId=none" style={{ fontWeight: seasonId === null ? "bold" : "normal" }}>
          No season
        </a>
      </nav>

      <p>
        Showing: {selectedSeason ? selectedSeason.name : "attempts taken outside any season"}
      </p>

      {rows.length === 0 && <p>No ranked sales reps yet for this season.</p>}

      <ol style={{ padding: 0, display: "flex", flexDirection: "column", gap: "0.5rem" }}>
        {rows.map((row, i) => (
          <li
            key={row.userId}
            style={{
              listStyle: "none",
              display: "flex",
              justifyContent: "space-between",
              border: "1px solid #ccc",
              borderRadius: 8,
              padding: "0.75rem 1rem",
            }}
          >
            <span>
              #{i + 1} {row.displayName} &mdash; <strong>{row.tierName}</strong>
            </span>
            <span>{row.score}</span>
          </li>
        ))}
      </ol>
    </main>
  );
}
