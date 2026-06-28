import { prisma } from "@/lib/prisma";
import StartAttemptButton from "./start-attempt-button";

export const dynamic = "force-dynamic";

export default async function CombinesPage() {
  const combines = await prisma.combine.findMany({
    where: { isActive: true },
    orderBy: { createdAt: "asc" },
    include: {
      combineScenarios: {
        include: { scenario: true },
        orderBy: { sortOrder: "asc" },
      },
    },
  });

  return (
    <main style={{ fontFamily: "system-ui", padding: "4rem 2rem", maxWidth: 720 }}>
      <h1>Combines</h1>
      {combines.length === 0 && <p>No combines available yet.</p>}
      <ul style={{ listStyle: "none", padding: 0, display: "flex", flexDirection: "column", gap: "1.5rem" }}>
        {combines.map((combine) => (
          <li key={combine.id} style={{ border: "1px solid #ccc", borderRadius: 8, padding: "1rem" }}>
            <h2>{combine.name}</h2>
            {combine.description && <p>{combine.description}</p>}
            <p>
              {combine.numScenarios} scenarios &middot; pass at {combine.cumulativeTarget} cumulative score,
              floor {combine.perScenarioFloor} per scenario
            </p>
            <ol>
              {combine.combineScenarios.map((cs) => (
                <li key={cs.id}>{cs.scenario.name}</li>
              ))}
            </ol>
            <StartAttemptButton combineId={combine.id} />
          </li>
        ))}
      </ul>
    </main>
  );
}
