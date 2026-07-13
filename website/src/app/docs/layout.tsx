import { DocsSidebar } from "@/components/docs/DocsSidebar";
import { DocsTableOfContents } from "@/components/docs/DocsTableOfContents";
import { DocsPageNavigation } from "@/components/docs/DocsPageNavigation";
import { MobileDocsSidebar } from "@/components/docs/MobileDocsSidebar";

export default function DocsLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="container mx-auto">
      <div className="flex gap-8 py-8">
        {/* Sidebar — hidden on mobile */}
        <aside className="hidden w-60 shrink-0 lg:block">
          <div className="sticky top-24 max-h-[calc(100vh-7rem)] overflow-y-auto pr-2">
            <DocsSidebar />
          </div>
        </aside>

        {/* Main content */}
        <div className="min-w-0 flex-1">
          <div className="mb-6 lg:hidden">
            <MobileDocsSidebar />
          </div>

          {/* data-pagefind-body scopes the search index to page content only. */}
          <article
            data-pagefind-body
            className="prose max-w-none prose-headings:scroll-mt-24 prose-a:font-medium prose-a:underline prose-a:underline-offset-2"
          >
            {children}
          </article>
          <DocsPageNavigation />
        </div>

        {/* On this page — hidden on smaller screens */}
        <aside className="hidden w-56 shrink-0 xl:block">
          <div className="sticky top-24">
            <DocsTableOfContents />
          </div>
        </aside>
      </div>
    </div>
  );
}
