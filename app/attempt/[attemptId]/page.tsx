import { redirect } from "next/navigation";
import { prisma } from "@/lib/prisma";
import { getCurrentUserId } from "@/lib/auth";
import VoiceSession from "./voice-session";

export const dynamic = "force-dynamic";

export default async function AttemptPage({
  params,
}: PageProps<"/attempt/[attemptId]">) {
  const { attemptId } = await params;
  const userId = await getCurrentUserId();
  if (!userId) redirect("/login");

  const attempt = await prisma.attempt.findUnique({ where: { id: attemptId } });
  if (!attempt || attempt.userId !== userId) redirect("/combines");

  const combineScenario = await prisma.combineScenario.findUnique({
    where: { combineId_sortOrder: { combineId: attempt.combineId, sortOrder: 0 } },
    include: { scenario: true },
  });
  if (!combineScenario) redirect("/combines");

  return (
    <main style={{ fontFamily: "system-ui", padding: "4rem 2rem", maxWidth: 720 }}>
      <h1>Attempt</h1>
      <p>Status: {attempt.status}</p>
      <VoiceSession attemptId={attempt.id} scenarioName={combineScenario.scenario.name} />
    </main>
  );
}
