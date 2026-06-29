"use client";

export default function Error({
  error,
  unstable_retry,
}: {
  error: Error & { digest?: string };
  unstable_retry: () => void;
}) {
  return (
    <main style={{ fontFamily: "system-ui", padding: "4rem 2rem", maxWidth: 480 }}>
      <h1>Something went wrong</h1>
      <p>{error.message || "An unexpected error occurred."}</p>
      <button onClick={() => unstable_retry()}>Try again</button>
    </main>
  );
}
