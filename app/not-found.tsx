import Link from "next/link";

export default function NotFound() {
  return (
    <main style={{ fontFamily: "system-ui", padding: "4rem 2rem", maxWidth: 480 }}>
      <h1>Not found</h1>
      <p>This page doesn&apos;t exist.</p>
      <Link href="/">Back to home</Link>
    </main>
  );
}
