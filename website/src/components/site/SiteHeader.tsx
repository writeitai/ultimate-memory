import Link from "next/link";
import { Github } from "lucide-react";
import { SearchCommand } from "@/components/search/SearchCommand";

export function SiteHeader() {
  return (
    <header className="sticky top-0 z-40 border-b border-border bg-background/80 backdrop-blur">
      <div className="container mx-auto flex h-16 items-center justify-between gap-4">
        <Link href="/" className="flex items-center gap-2 font-semibold">
          <span
            aria-hidden
            className="inline-block h-5 w-5 rounded-full border-2 border-brand"
          />
          <span>Ultimate Memory</span>
        </Link>

        <div className="flex items-center gap-2 sm:gap-4">
          <SearchCommand />
          <Link
            href="/docs"
            className="hidden text-sm text-muted-foreground hover:text-foreground sm:inline"
          >
            Docs
          </Link>
          <a
            href="https://github.com/writeitai/ultimate-memory"
            target="_blank"
            rel="noreferrer"
            className="text-muted-foreground hover:text-foreground"
            aria-label="ultimate-memory on GitHub"
          >
            <Github className="h-5 w-5" />
          </a>
        </div>
      </div>
    </header>
  );
}
