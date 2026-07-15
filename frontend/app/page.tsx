export default function Home() {
  return (
    <main className="mx-auto flex min-h-screen max-w-3xl flex-col justify-center gap-6 px-6 py-24">
      <span className="text-sm font-medium uppercase tracking-widest text-avms-accent">
        AVMS · Phase 0
      </span>
      <h1 className="text-4xl font-semibold sm:text-5xl">
        Agentic Visual Merchandising Studio
      </h1>
      <p className="text-lg text-slate-600">
        Upload a display photo. A council of specialist agents will return nine
        brand-aware recommendations and a mock-up of the improved display.
      </p>
      <p className="text-sm text-slate-500">
        Frontend scaffold ready. Auth, upload, and analysis views land in Phase 1.
      </p>
    </main>
  );
}
