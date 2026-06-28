# LAMNA

Ranked AI sales training. Salespeople take a "Combine" — a series of
AI-voice sales roleplay scenarios graded by Claude — and earn public,
revocable, shark-themed rank tiers.

## Stack

- Next.js (App Router) — full-stack, deployed on Railway
- Postgres (Railway) via Prisma
- JWT auth (`jose` + httpOnly cookies + bcrypt)
- OpenAI Realtime API for in-browser voice roleplay
- Claude (Anthropic API) for post-conversation transcript grading

## Development

```bash
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000). `GET /api/health`
returns `{ status: "ok" }` once the app is running.

## Build status

Being built incrementally per the LAMNA build plan — schema, auth, the
Combine engine, voice scenarios, grading, tiers, seasons, leaderboard,
and dashboards land in that order, each step independently deployable.
