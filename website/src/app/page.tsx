import Link from "next/link";
import { ArrowRight, Github } from "lucide-react";

export default function Home() {
  return (
    <div className="container mx-auto flex flex-col items-center px-4 py-24 text-center sm:py-32">
      <span className="mb-6 inline-flex items-center rounded-full border border-border bg-card px-3 py-1 text-xs font-medium text-muted-foreground">
        Open source · In development — design complete, build under way
      </span>

      <h1 className="max-w-3xl text-4xl font-bold tracking-tight sm:text-5xl">
        A memory system for AI agents, built for millions of documents.
      </h1>

      <p className="mt-6 max-w-2xl text-lg text-muted-foreground">
        <span className="font-semibold text-foreground">Ultimate Memory</span>{" "}
        ingests heterogeneous documents — files, mail, recordings, images — and
        distills them into progressively more abstract, navigable knowledge:
        immutable evidence, adjudicated facts, and compiled understanding. Every
        answer traces back to its sources, and everything stays auditable by
        humans.
      </p>

      <div className="mt-10 flex flex-col items-center gap-4 sm:flex-row">
        <Link
          href="/docs"
          className="inline-flex items-center gap-2 rounded-md bg-primary px-5 py-2.5 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90"
        >
          Read the docs
          <ArrowRight className="h-4 w-4" />
        </Link>
        <a
          href="https://github.com/writeitai/ultimate-memory"
          target="_blank"
          rel="noreferrer"
          className="inline-flex items-center gap-2 rounded-md border border-border px-5 py-2.5 text-sm font-medium text-foreground transition-colors hover:bg-accent/50"
        >
          <Github className="h-4 w-4" />
          View on GitHub
        </a>
      </div>

      <div className="mt-12 w-full max-w-md">
        <div className="overflow-x-auto rounded-lg border border-border bg-card px-5 py-4 text-left font-mono text-sm">
          <span className="text-muted-foreground select-none">
            E — what we ingested · K — what we concluded · P — how we reach it
          </span>
        </div>
      </div>
    </div>
  );
}
