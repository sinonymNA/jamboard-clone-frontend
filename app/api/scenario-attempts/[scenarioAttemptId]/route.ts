import { prisma } from "@/lib/prisma";
import { getCurrentUserId } from "@/lib/auth";
import { gradeScenarioAttempt } from "@/lib/grading";

export async function PATCH(
  request: Request,
  ctx: RouteContext<"/api/scenario-attempts/[scenarioAttemptId]">
) {
  const userId = await getCurrentUserId();
  if (!userId) return Response.json({ error: "not authenticated" }, { status: 401 });

  const { scenarioAttemptId } = await ctx.params;
  const scenarioAttempt = await prisma.scenarioAttempt.findUnique({
    where: { id: scenarioAttemptId },
    include: { attempt: true },
  });
  if (!scenarioAttempt || scenarioAttempt.attempt.userId !== userId) {
    return Response.json({ error: "scenario attempt not found" }, { status: 404 });
  }

  const body = await request.json().catch(() => null);
  if (!Array.isArray(body?.transcript)) {
    return Response.json({ error: "transcript array is required" }, { status: 400 });
  }

  const updated = await prisma.scenarioAttempt.update({
    where: { id: scenarioAttemptId },
    data: { transcript: body.transcript, completedAt: new Date() },
  });

  let gradingError: string | null = null;
  try {
    await gradeScenarioAttempt(scenarioAttemptId);
  } catch (err) {
    console.error("scenario attempt grading failed", scenarioAttemptId, err);
    gradingError = "grading is temporarily unavailable; this scenario will be retried later";
  }

  const graded = await prisma.scenarioAttempt.findUnique({
    where: { id: scenarioAttemptId },
    include: { scores: true },
  });

  return Response.json({ scenarioAttempt: graded ?? updated, gradingError });
}
