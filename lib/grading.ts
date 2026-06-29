import Anthropic from "@anthropic-ai/sdk";
import { zodOutputFormat } from "@anthropic-ai/sdk/helpers/zod";
import { z } from "zod";
import { prisma } from "@/lib/prisma";

const GRADING_MODEL = "claude-opus-4-8";

const FeedbackQuoteSchema = z.object({
  transcriptExcerpt: z.string(),
  comment: z.string(),
});

const DimensionScoreSchema = z.object({
  dimensionName: z.string(),
  score: z.number().int().min(0).max(100),
  feedbackSummary: z.string(),
  feedbackQuotes: z.array(FeedbackQuoteSchema),
});

const GradingResultSchema = z.object({
  scores: z.array(DimensionScoreSchema),
});

type TranscriptEntry = { role: "user" | "assistant"; text: string; timestamp: string };

function buildPrompt(
  scenarioName: string,
  personaPrompt: string,
  transcript: TranscriptEntry[],
  dimensions: { name: string; description: string | null }[]
) {
  const transcriptText = transcript
    .map((entry) => `[${entry.role}] ${entry.text}`)
    .join("\n");

  const rubricText = dimensions
    .map((d) => `- ${d.name}${d.description ? `: ${d.description}` : ""}`)
    .join("\n");

  return `You are grading a sales roleplay call transcript. The salesperson (role "user") was practicing against an AI persona (role "assistant") in the following scenario:

Scenario: ${scenarioName}
Persona briefing given to the AI: ${personaPrompt}

Transcript:
${transcriptText}

Score the salesperson's performance on each of the following dimensions, from 0-100:
${rubricText}

For each dimension, write a specific feedbackSummary tied to what actually happened in this call — never generic advice that could apply to any call. Back up the score with feedbackQuotes: short verbatim excerpts from the transcript paired with a comment explaining what the excerpt shows about that dimension. Every dimension must have at least one feedbackQuote unless the transcript is too short to support one.`;
}

export async function gradeScenarioAttempt(scenarioAttemptId: string) {
  const scenarioAttempt = await prisma.scenarioAttempt.findUnique({
    where: { id: scenarioAttemptId },
    include: {
      combineScenario: {
        include: {
          scenario: true,
          combine: true,
          dimensionLinks: { include: { dimension: true } },
        },
      },
    },
  });
  if (!scenarioAttempt) throw new Error("scenario attempt not found");

  const { combineScenario } = scenarioAttempt;
  const dimensionLinks = combineScenario.dimensionLinks.filter((link) => link.dimension.isActive);
  if (dimensionLinks.length === 0) {
    throw new Error("combine scenario has no active dimensions configured");
  }

  const transcript = Array.isArray(scenarioAttempt.transcript)
    ? (scenarioAttempt.transcript as unknown as TranscriptEntry[])
    : [];

  const client = new Anthropic();
  const message = await client.messages.parse({
    model: GRADING_MODEL,
    max_tokens: 4096,
    output_config: { format: zodOutputFormat(GradingResultSchema) },
    messages: [
      {
        role: "user",
        content: buildPrompt(
          combineScenario.scenario.name,
          combineScenario.scenario.personaPrompt,
          transcript,
          dimensionLinks.map((link) => ({ name: link.dimension.name, description: link.dimension.description }))
        ),
      },
    ],
  });

  if (message.stop_reason === "refusal") {
    throw new Error("grading request was refused by the model");
  }
  if (!message.parsed_output) {
    throw new Error("grading response could not be parsed");
  }

  const scoreByName = new Map(message.parsed_output.scores.map((s) => [s.dimensionName, s]));

  const scoreRows = dimensionLinks.map((link) => {
    const result = scoreByName.get(link.dimension.name);
    if (!result) {
      throw new Error(`grading response is missing dimension "${link.dimension.name}"`);
    }
    return { link, result };
  });

  const totalWeight = scoreRows.reduce((sum, { link }) => sum + link.weight, 0);
  const weightedScore =
    totalWeight > 0
      ? scoreRows.reduce((sum, { link, result }) => sum + result.score * link.weight, 0) / totalWeight
      : 0;
  const rollupScore = Math.round(weightedScore);
  const floorBreached = rollupScore < combineScenario.combine.perScenarioFloor;

  await prisma.$transaction([
    ...scoreRows.map(({ link, result }) =>
      prisma.scenarioScore.upsert({
        where: { scenarioAttemptId_dimensionId: { scenarioAttemptId, dimensionId: link.dimensionId } },
        create: {
          scenarioAttemptId,
          dimensionId: link.dimensionId,
          rawScore: result.score,
          verifiedScore: result.score,
          feedbackSummary: result.feedbackSummary,
          feedbackQuotes: result.feedbackQuotes,
        },
        update: {
          rawScore: result.score,
          verifiedScore: result.score,
          feedbackSummary: result.feedbackSummary,
          feedbackQuotes: result.feedbackQuotes,
        },
      })
    ),
    prisma.scenarioAttempt.update({
      where: { id: scenarioAttemptId },
      data: { rollupScore, floorBreached },
    }),
  ]);

  return { rollupScore, floorBreached };
}
