export type NavItem = {
  title: string;
  href: string;
  children?: NavItem[];
};

// Single source of truth for the docs sidebar order and grouping. It also
// drives prev/next pagination. Add a page here when you add its page.mdx.
export const docsNavigation: NavItem[] = [
  { title: "Introduction", href: "/docs" },
  { title: "Concepts", href: "/docs/concepts" },
  { title: "Architecture", href: "/docs/architecture" },
  { title: "Project Status", href: "/docs/project-status" },
  {
    title: "Reference",
    href: "/docs/reference/api",
    children: [
      { title: "API Reference", href: "/docs/reference/api" },
      { title: "CLI Reference", href: "/docs/reference/cli" },
      { title: "MCP Reference", href: "/docs/reference/mcp" },
    ],
  },
];

export function flattenNavigation(items: NavItem[]): NavItem[] {
  const result: NavItem[] = [];
  for (const item of items) {
    result.push(item);
    if (item.children) {
      result.push(...flattenNavigation(item.children));
    }
  }
  return result;
}

export function findAdjacentPages(pathname: string): {
  prev: NavItem | null;
  next: NavItem | null;
} {
  // De-duplicate on href so a section header that points at its first child
  // (e.g. "Reference" -> Session Layout) does not create a self-adjacency.
  const seen = new Set<string>();
  const flat = flattenNavigation(docsNavigation).filter((item) => {
    if (seen.has(item.href)) return false;
    seen.add(item.href);
    return true;
  });

  const normalize = (p: string) => (p.length > 1 ? p.replace(/\/$/, "") : p);
  const target = normalize(pathname);
  const index = flat.findIndex((item) => normalize(item.href) === target);
  if (index === -1) {
    return { prev: null, next: null };
  }
  return {
    prev: index > 0 ? flat[index - 1] : null,
    next: index < flat.length - 1 ? flat[index + 1] : null,
  };
}
