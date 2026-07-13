"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { findAdjacentPages } from "@/lib/docs/navigation";

export function DocsPageNavigation() {
  const pathname = usePathname();
  const { prev, next } = findAdjacentPages(pathname);

  if (!prev && !next) {
    return null;
  }

  return (
    <nav className="mt-12 flex items-center justify-between border-t border-border pt-6">
      {prev ? (
        <Link
          href={prev.href}
          className="group flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
        >
          <ChevronLeft className="h-4 w-4 transition-transform group-hover:-translate-x-0.5" />
          {prev.title}
        </Link>
      ) : (
        <div />
      )}
      {next ? (
        <Link
          href={next.href}
          className="group flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
        >
          {next.title}
          <ChevronRight className="h-4 w-4 transition-transform group-hover:translate-x-0.5" />
        </Link>
      ) : (
        <div />
      )}
    </nav>
  );
}
