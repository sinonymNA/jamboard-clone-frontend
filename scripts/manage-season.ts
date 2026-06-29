import "dotenv/config";
import { createSeason, activateSeason, closeCurrentSeason, listSeasons } from "../lib/season-admin";
import { prisma } from "../lib/prisma";

function usage(): never {
  console.error(
    [
      "Usage:",
      '  npm run season -- list',
      '  npm run season -- create "<name>" <startsAtISO> <endsAtISO>',
      '  npm run season -- activate "<name>"',
      "  npm run season -- close",
    ].join("\n")
  );
  process.exit(1);
}

async function main() {
  const [cmd, ...args] = process.argv.slice(2);

  if (cmd === "list") {
    const seasons = await listSeasons();
    if (seasons.length === 0) {
      console.log("no seasons yet");
      return;
    }
    for (const s of seasons) {
      console.log(`${s.isActive ? "* " : "  "}${s.name}  ${s.startsAt.toISOString()} -> ${s.endsAt.toISOString()}  (id=${s.id})`);
    }
    return;
  }

  if (cmd === "create") {
    const [name, startsAt, endsAt] = args;
    if (!name || !startsAt || !endsAt) usage();
    const season = await createSeason(name, new Date(startsAt), new Date(endsAt));
    console.log(`created season "${season.name}" (id=${season.id}), inactive until activated`);
    return;
  }

  if (cmd === "activate") {
    const [name] = args;
    if (!name) usage();
    const season = await activateSeason(name);
    console.log(`activated season "${season.name}" (id=${season.id}); any previously active season was closed`);
    return;
  }

  if (cmd === "close") {
    const closed = await closeCurrentSeason();
    console.log(closed ? `closed season "${closed.name}" (id=${closed.id})` : "no season was active");
    return;
  }

  usage();
}

main()
  .catch((err) => {
    console.error(err.message ?? err);
    process.exitCode = 1;
  })
  .finally(() => prisma.$disconnect());
