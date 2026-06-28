import { redirect } from "next/navigation";
import { getCurrentUserId } from "@/lib/auth";
import { prisma } from "@/lib/prisma";
import LogoutButton from "./logout-button";

export default async function ProfilePage() {
  const userId = await getCurrentUserId();
  if (!userId) redirect("/login");

  const user = await prisma.user.findUnique({
    where: { id: userId },
    include: { entitlement: true },
  });
  if (!user) redirect("/login");

  return (
    <main style={{ fontFamily: "system-ui", padding: "4rem 2rem", maxWidth: 480 }}>
      <h1>{user.displayName}</h1>
      <p>{user.email}</p>
      <p>Plan: {user.entitlement?.plan ?? "FREE (no entitlement record yet)"}</p>
      <p>Member since {user.createdAt.toLocaleDateString()}</p>
      <LogoutButton />
    </main>
  );
}
