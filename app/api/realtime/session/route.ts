import { prisma } from "@/lib/prisma";
import { getCurrentUserId } from "@/lib/auth";

const OPENAI_REALTIME_MODEL = "gpt-realtime";

export async function POST(request: Request) {
  const userId = await getCurrentUserId();
  if (!userId) return Response.json({ error: "not authenticated" }, { status: 401 });

  const body = await request.json().catch(() => null);
  const attemptId = typeof body?.attemptId === "string" ? body.attemptId : "";
  if (!attemptId) return Response.json({ error: "attemptId is required" }, { status: 400 });

  const attempt = await prisma.attempt.findUnique({ where: { id: attemptId } });
  if (!attempt || attempt.userId !== userId) {
    return Response.json({ error: "attempt not found" }, { status: 404 });
  }
  if (attempt.status !== "IN_PROGRESS") {
    return Response.json({ error: "attempt is not in progress" }, { status: 409 });
  }

  const combineScenarios = await prisma.combineScenario.findMany({
    where: { combineId: attempt.combineId },
    orderBy: { sortOrder: "asc" },
    include: { scenario: true, scenarioAttempts: { where: { attemptId: attempt.id } } },
  });
  if (combineScenarios.length === 0) {
    return Response.json({ error: "combine has no scenarios configured" }, { status: 500 });
  }

  const next = combineScenarios.find((cs) => !cs.scenarioAttempts[0]?.completedAt);
  if (!next) {
    return Response.json({ error: "all scenarios in this combine are already completed" }, { status: 409 });
  }
  const combineScenario = next;

  let scenarioAttempt = combineScenario.scenarioAttempts[0] ?? null;
  if (!scenarioAttempt) {
    scenarioAttempt = await prisma.scenarioAttempt.create({
      data: { attemptId: attempt.id, combineScenarioId: combineScenario.id, transcript: [] },
    });
  }

  const apiKey = process.env.OPENAI_API_KEY;
  if (!apiKey) {
    return Response.json({ error: "voice roleplay is not configured" }, { status: 503 });
  }

  const scenario = combineScenario.scenario;
  const openaiRes = await fetch("https://api.openai.com/v1/realtime/client_secrets", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${apiKey}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      expires_after: { anchor: "created_at", seconds: 600 },
      session: {
        type: "realtime",
        model: OPENAI_REALTIME_MODEL,
        instructions: scenario.personaPrompt,
        ...(scenario.voiceConfig && typeof scenario.voiceConfig === "object" ? scenario.voiceConfig : {}),
      },
    }),
  });

  if (!openaiRes.ok) {
    const detail = await openaiRes.text().catch(() => "");
    console.error("OpenAI realtime client_secrets error", openaiRes.status, detail);
    return Response.json({ error: "could not start voice session" }, { status: 502 });
  }

  const session = await openaiRes.json();

  return Response.json({
    scenarioAttemptId: scenarioAttempt.id,
    clientSecret: session.value,
    expiresAt: session.expires_at,
    model: OPENAI_REALTIME_MODEL,
    scenario: { name: scenario.name, description: scenario.description },
  });
}
