import { prisma } from "@/lib/prisma";

function Sparkline({ values }: { values: number[] }) {
  if (values.length < 2) return null;
  const width = 160;
  const height = 32;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const points = values
    .map((v, i) => {
      const x = (i / (values.length - 1)) * width;
      const y = height - ((v - min) / range) * height;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  return (
    <svg width={width} height={height} style={{ display: "block" }}>
      <polyline points={points} fill="none" stroke="#2563eb" strokeWidth={2} />
    </svg>
  );
}

export default async function PaidInsights({ userId }: { userId: string }) {
  const [scores, attempts] = await Promise.all([
    prisma.scenarioScore.findMany({
      where: { scenarioAttempt: { attempt: { userId } } },
      include: { dimension: true, scenarioAttempt: { select: { completedAt: true } } },
      orderBy: { scenarioAttempt: { completedAt: "asc" } },
    }),
    prisma.attempt.findMany({
      where: { userId },
      include: { combine: true },
      orderBy: { startedAt: "desc" },
    }),
  ]);

  const byDimension = new Map<string, number[]>();
  for (const score of scores) {
    const list = byDimension.get(score.dimension.name) ?? [];
    list.push(score.verifiedScore);
    byDimension.set(score.dimension.name, list);
  }

  return (
    <>
      <section style={{ border: "1px solid #ccc", borderRadius: 8, padding: "1rem", marginBottom: "1.5rem" }}>
        <h2>Dimension trends</h2>
        {byDimension.size === 0 && <p>Complete a scenario to start tracking dimension trends.</p>}
        <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
          {Array.from(byDimension.entries()).map(([name, values]) => {
            const delta = values.length >= 2 ? values[values.length - 1] - values[values.length - 2] : null;
            return (
              <div key={name} style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
                <span style={{ width: 160 }}>{name}</span>
                <Sparkline values={values} />
                <span>
                  {values[values.length - 1]}
                  {delta !== null && (
                    <span style={{ color: delta >= 0 ? "green" : "crimson" }}>
                      {" "}
                      ({delta >= 0 ? "+" : ""}
                      {delta})
                    </span>
                  )}
                </span>
              </div>
            );
          })}
        </div>
      </section>

      <section style={{ border: "1px solid #ccc", borderRadius: 8, padding: "1rem", marginBottom: "1.5rem" }}>
        <h2>Attempt log</h2>
        {attempts.length === 0 && <p>No attempts yet.</p>}
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ textAlign: "left" }}>
              <th>Combine</th>
              <th>Status</th>
              <th>Score</th>
              <th>Result</th>
              <th>Started</th>
            </tr>
          </thead>
          <tbody>
            {attempts.map((a) => (
              <tr key={a.id}>
                <td>{a.combine.name}</td>
                <td>{a.status}</td>
                <td>{a.cumulativeScore ?? "—"}</td>
                <td>{a.passed === null ? "—" : a.passed ? "Passed" : "Failed"}</td>
                <td>{a.startedAt.toLocaleDateString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </>
  );
}
