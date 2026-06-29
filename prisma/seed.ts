import "dotenv/config";
import { PrismaPg } from "@prisma/adapter-pg";
import { PrismaClient } from "../generated/prisma/client";

const adapter = new PrismaPg({ connectionString: process.env.DATABASE_URL });
const prisma = new PrismaClient({ adapter });

async function main() {
  const dimensions = await Promise.all(
    [
      { name: "rapport", description: "Builds genuine connection and trust early in the conversation." },
      { name: "discovery", description: "Asks probing questions to uncover the prospect's real needs and constraints." },
      { name: "objection_handling", description: "Responds to pushback with specific, credible counters rather than generic reassurance." },
      { name: "value_framing", description: "Ties the product's value to the prospect's stated priorities, not a generic pitch." },
      { name: "closing", description: "Drives toward a clear next step or commitment without being pushy." },
    ].map((d) =>
      prisma.dimension.upsert({
        where: { name: d.name },
        update: { description: d.description },
        create: d,
      })
    )
  );

  const scenarios = await Promise.all(
    [
      {
        name: "Skeptical IT Director",
        description: "A budget-conscious IT director who has been burned by vendors before.",
        personaPrompt:
          "You are Dana Reyes, an IT Director at a mid-size logistics company. You are skeptical of vendor pitches because a previous tool overpromised and underdelivered. You ask pointed questions about implementation cost, security, and support SLAs. You only warm up if the salesperson asks about your actual pain points before pitching. Stay in character for the entire call; do not break the roleplay.",
        voiceConfig: { voice: "ash", temperature: 0.7 },
      },
      {
        name: "Indecisive Small Business Owner",
        description: "An owner who likes the product but is anxious about cost and timing.",
        personaPrompt:
          "You are Marcus Webb, the owner of a 12-person retail business. You're interested but conflict-averse and tend to stall with 'let me think about it.' You respond well to salespeople who acknowledge your hesitation directly and offer a low-risk next step. You push back softly on price. Stay in character for the entire call; do not break the roleplay.",
        voiceConfig: { voice: "verse", temperature: 0.8 },
      },
      {
        name: "Fast-Talking Procurement Lead",
        description: "A time-pressured procurement lead who wants the pitch compressed to bullet points.",
        personaPrompt:
          "You are Priya Nair, a procurement lead juggling six vendor calls today. You interrupt rambling pitches and ask for the bottom line. You respect salespeople who are concise and who tie features directly to ROI. You end the call abruptly if the pitch is generic or unfocused. Stay in character for the entire call; do not break the roleplay.",
        voiceConfig: { voice: "ballad", temperature: 0.6 },
      },
    ].map(async (s) => {
      const existing = await prisma.scenario.findFirst({ where: { name: s.name } });
      if (existing) {
        return prisma.scenario.update({
          where: { id: existing.id },
          data: { description: s.description, personaPrompt: s.personaPrompt, voiceConfig: s.voiceConfig },
        });
      }
      return prisma.scenario.create({ data: s });
    })
  );

  const dimensionByName = Object.fromEntries(dimensions.map((d) => [d.name, d]));
  const scenarioByName = Object.fromEntries(scenarios.map((s) => [s.name, s]));

  const combine =
    (await prisma.combine.findFirst({ where: { name: "Cold Call Combine" } })) ??
    (await prisma.combine.create({
      data: {
        name: "Cold Call Combine",
        description: "Three back-to-back cold-call roleplays covering a range of buyer temperaments.",
        numScenarios: scenarios.length,
        cumulativeTarget: 210,
        perScenarioFloor: 50,
        isActive: true,
      },
    }));

  const scenarioOrder = ["Skeptical IT Director", "Indecisive Small Business Owner", "Fast-Talking Procurement Lead"];

  for (let i = 0; i < scenarioOrder.length; i++) {
    const scenario = scenarioByName[scenarioOrder[i]];
    const combineScenario = await prisma.combineScenario.upsert({
      where: { combineId_sortOrder: { combineId: combine.id, sortOrder: i } },
      update: { scenarioId: scenario.id },
      create: { combineId: combine.id, scenarioId: scenario.id, sortOrder: i },
    });

    for (const dimensionName of ["rapport", "discovery", "objection_handling", "value_framing", "closing"]) {
      const dimension = dimensionByName[dimensionName];
      await prisma.combineScenarioDimension.upsert({
        where: {
          combineScenarioId_dimensionId: {
            combineScenarioId: combineScenario.id,
            dimensionId: dimension.id,
          },
        },
        update: {},
        create: { combineScenarioId: combineScenario.id, dimensionId: dimension.id, weight: 1.0 },
      });
    }
  }

  const tiers = await Promise.all(
    [
      { name: "Minnow", rankOrder: 1, passThreshold: 0, description: "Cleared a Combine for the first time." },
      { name: "Reef", rankOrder: 2, passThreshold: 150, description: "Consistently solid cold-call performance." },
      { name: "Mako", rankOrder: 3, passThreshold: 220, description: "Sharp, well-rounded sales execution." },
      { name: "Apex", rankOrder: 4, passThreshold: 270, description: "Elite, near-flawless Combine performance." },
    ].map((t) =>
      prisma.tier.upsert({
        where: { name: t.name },
        update: { rankOrder: t.rankOrder, passThreshold: t.passThreshold, description: t.description },
        create: t,
      })
    )
  );

  console.log(
    `Seeded ${dimensions.length} dimensions, ${scenarios.length} scenarios, 1 combine ("${combine.name}"), ${tiers.length} tiers.`
  );
}

main()
  .catch((e) => {
    console.error(e);
    process.exitCode = 1;
  })
  .finally(async () => {
    await prisma.$disconnect();
  });
