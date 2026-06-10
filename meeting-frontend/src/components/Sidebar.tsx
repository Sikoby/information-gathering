import { useEffect, useState } from "react";
import { cn } from "@ig/ui";
import { childrenOf, scheduledNodes } from "@/types";
import type { MeetingState } from "@/types";

type NavItem = {
  id: string;
  label: string;
  children?: NavItem[];
};

function buildItems(state: MeetingState): NavItem[] {
  const phases = scheduledNodes(state.sections);
  return [
    { id: "breadcrumb", label: "Position" },
    {
      id: "agenda",
      label: "Agenda",
    },
    {
      id: "notebook",
      label: "Notebook",
      children: phases.map((p) => ({
        id: `section-${p.id}`,
        label: p.header,
        children: childrenOf(state.sections, p.id)
          .filter((s) => s.kind === "topic")
          .map((t) => ({ id: `section-${t.id}`, label: t.header })),
      })),
    },
    { id: "followups", label: "Follow-ups" },
    { id: "briefing", label: "Briefing" },
  ];
}

function flattenIds(items: NavItem[]): string[] {
  const out: string[] = [];
  for (const item of items) {
    out.push(item.id);
    if (item.children) out.push(...flattenIds(item.children));
  }
  return out;
}

export function Sidebar({ state, className }: { state: MeetingState; className?: string }) {
  const items = buildItems(state);
  const [activeId, setActiveId] = useState<string>(items[0]?.id ?? "");

  useEffect(() => {
    const ids = flattenIds(items);
    const nodes = ids
      .map((id) => document.getElementById(id))
      .filter((n): n is HTMLElement => n !== null);
    if (nodes.length === 0) return;

    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((e) => e.isIntersecting)
          .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
        if (visible.length > 0) setActiveId(visible[0].target.id);
      },
      {
        rootMargin: "-20% 0px -60% 0px",
        threshold: 0,
      },
    );
    for (const node of nodes) observer.observe(node);
    return () => observer.disconnect();
  }, [state.sections.length]);

  const handleClick = (e: React.MouseEvent<HTMLAnchorElement>, id: string) => {
    e.preventDefault();
    const node = document.getElementById(id);
    if (node) {
      node.scrollIntoView({ behavior: "smooth", block: "start" });
      setActiveId(id);
      history.replaceState(null, "", `#${id}`);
    }
  };

  const renderItem = (item: NavItem, depth = 0) => {
    const isActive = activeId === item.id;
    return (
      <li key={item.id}>
        <a
          href={`#${item.id}`}
          onClick={(e) => handleClick(e, item.id)}
          className={cn(
            "block rounded px-2 py-1 transition-colors",
            depth === 0 && "text-sm font-medium",
            depth === 1 && "pl-4 text-xs",
            depth >= 2 && "pl-6 text-[11px]",
            isActive
              ? "bg-secondary text-foreground"
              : "text-muted-foreground hover:bg-secondary/50 hover:text-foreground",
          )}
        >
          {item.label}
        </a>
        {item.children && item.children.length > 0 && (
          <ul className="mt-1 space-y-0.5">
            {item.children.map((child) => renderItem(child, depth + 1))}
          </ul>
        )}
      </li>
    );
  };

  return (
    <nav
      aria-label="Page sections"
      className={cn("sticky top-4 self-start hidden md:block", className)}
    >
      <p className="mb-2 px-2 text-[10px] uppercase tracking-wide text-muted-foreground">
        On this page
      </p>
      <ul className="space-y-1">{items.map((item) => renderItem(item))}</ul>
    </nav>
  );
}
