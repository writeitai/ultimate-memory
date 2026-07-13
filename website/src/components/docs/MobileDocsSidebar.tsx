"use client";

import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import * as Dialog from "@radix-ui/react-dialog";
import { Menu, X } from "lucide-react";
import { DocsSidebar } from "./DocsSidebar";

export function MobileDocsSidebar() {
  const [isOpen, setIsOpen] = useState(false);
  const pathname = usePathname();

  // Close the drawer on navigation.
  useEffect(() => {
    setIsOpen(false);
  }, [pathname]);

  // Radix Dialog handles focus trapping, focus restoration, scroll lock,
  // Escape-to-close, and role/aria-modal semantics.
  return (
    <Dialog.Root open={isOpen} onOpenChange={setIsOpen}>
      <Dialog.Trigger asChild>
        <button
          type="button"
          className="flex items-center gap-2 rounded-md border border-border px-3 py-2 text-sm text-muted-foreground hover:text-foreground lg:hidden"
          aria-label="Open navigation menu"
        >
          <Menu className="h-4 w-4" />
          Menu
        </button>
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/50 lg:hidden" />
        <Dialog.Content
          className="fixed inset-y-0 left-0 z-50 w-72 overflow-y-auto bg-background p-6 shadow-lg outline-none lg:hidden"
          aria-describedby={undefined}
        >
          <div className="mb-6 flex items-center justify-between">
            <Dialog.Title className="text-sm font-medium text-foreground">
              Documentation
            </Dialog.Title>
            <Dialog.Close
              className="rounded-md p-1 text-muted-foreground hover:text-foreground"
              aria-label="Close navigation menu"
            >
              <X className="h-4 w-4" />
            </Dialog.Close>
          </div>
          <DocsSidebar />
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
