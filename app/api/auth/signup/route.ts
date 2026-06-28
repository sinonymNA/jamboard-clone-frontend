import { prisma } from "@/lib/prisma";
import { hashPassword, signSessionToken, setSessionCookie } from "@/lib/auth";

export async function POST(request: Request) {
  const body = await request.json().catch(() => null);
  const email = typeof body?.email === "string" ? body.email.trim().toLowerCase() : "";
  const password = typeof body?.password === "string" ? body.password : "";
  const displayName = typeof body?.displayName === "string" ? body.displayName.trim() : "";

  if (!email || !password || !displayName) {
    return Response.json(
      { error: "email, password, and displayName are required" },
      { status: 400 }
    );
  }
  if (password.length < 8) {
    return Response.json(
      { error: "password must be at least 8 characters" },
      { status: 400 }
    );
  }

  const existing = await prisma.user.findUnique({ where: { email } });
  if (existing) {
    return Response.json({ error: "an account with that email already exists" }, { status: 409 });
  }

  const passwordHash = await hashPassword(password);
  const user = await prisma.user.create({
    data: { email, passwordHash, displayName },
  });

  const token = await signSessionToken(user.id);
  await setSessionCookie(token);

  return Response.json({
    user: { id: user.id, email: user.email, displayName: user.displayName },
  });
}
