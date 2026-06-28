import { prisma } from "@/lib/prisma";
import { verifyPassword, signSessionToken, setSessionCookie } from "@/lib/auth";

export async function POST(request: Request) {
  const body = await request.json().catch(() => null);
  const email = typeof body?.email === "string" ? body.email.trim().toLowerCase() : "";
  const password = typeof body?.password === "string" ? body.password : "";

  if (!email || !password) {
    return Response.json({ error: "email and password are required" }, { status: 400 });
  }

  const user = await prisma.user.findUnique({ where: { email } });
  if (!user || !(await verifyPassword(password, user.passwordHash))) {
    return Response.json({ error: "invalid email or password" }, { status: 401 });
  }

  const token = await signSessionToken(user.id);
  await setSessionCookie(token);

  return Response.json({
    user: { id: user.id, email: user.email, displayName: user.displayName },
  });
}
