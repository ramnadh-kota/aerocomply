"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { searchAll, type SearchResult, type SearchResultType } from "@/lib/mock/search";

const TYPE_ORDER: SearchResultType[] = [
  "Aircraft",
  "Engine",
  "Component",
  "Part",
  "WorkOrder",
  "Technician",
  "Vendor",
  "PurchaseOrder",
  "Regulation",
];

const MAX_PER_GROUP = 6;

function groupResults(results: SearchResult[]): Array<{ type: SearchResultType; items: SearchResult[] }> {
  const groups: Array<{ type: SearchResultType; items: SearchResult[] }> = [];
  for (const type of TYPE_ORDER) {
    const items = results.filter((r) => r.type === type).slice(0, MAX_PER_GROUP);
    if (items.length > 0) groups.push({ type, items });
  }
  return groups;
}

export function GlobalSearch() {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);

  const results = useMemo(() => searchAll(query), [query]);
  const groups = useMemo(() => groupResults(results), [results]);
  const flatResults = useMemo(() => groups.flatMap((g) => g.items), [groups]);
  const [activeIndex, setActiveIndex] = useState(-1);

  useEffect(() => {
    setActiveIndex(-1);
  }, [query]);

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      const isCmdK = (e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k";
      if (isCmdK) {
        e.preventDefault();
        inputRef.current?.focus();
        inputRef.current?.select();
        setOpen(true);
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  function go(href: string) {
    setOpen(false);
    setQuery("");
    router.push(href);
  }

  function onInputKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (!open || flatResults.length === 0) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActiveIndex((i) => (i + 1) % flatResults.length);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActiveIndex((i) => (i - 1 + flatResults.length) % flatResults.length);
    } else if (e.key === "Enter" && activeIndex >= 0) {
      e.preventDefault();
      go(flatResults[activeIndex].href);
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  }

  return (
    <div style={{ position: "relative", flex: 1, maxWidth: 420 }}>
      <input
        ref={inputRef}
        type="search"
        className="ac-input"
        placeholder="Search aircraft, work orders, parts, vendors… (Ctrl/Cmd+K)"
        aria-label="Global search"
        value={query}
        onChange={(e) => {
          setQuery(e.target.value);
          setOpen(true);
        }}
        onKeyDown={onInputKeyDown}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
      />
      {open && query.trim() && (
        <div
          role="listbox"
          className="ac-card"
          style={{
            position: "absolute",
            top: "calc(100% + 6px)",
            left: 0,
            right: 0,
            zIndex: 50,
            padding: "var(--ac-space-2)",
            maxHeight: 420,
            overflowY: "auto",
          }}
        >
          {flatResults.length === 0 && (
            <div className="ac-text-sm ac-text-muted" style={{ padding: 8 }}>
              No results for &ldquo;{query}&rdquo;
            </div>
          )}
          {groups.map((group) => (
            <div key={group.type} style={{ marginBottom: 6 }}>
              <p className="ac-eyebrow" style={{ margin: "6px 8px 2px" }}>
                {group.type === "WorkOrder" ? "Work Orders" : group.type === "PurchaseOrder" ? "Purchase Orders" : `${group.type}s`}
              </p>
              {group.items.map((r) => {
                const flatIdx = flatResults.indexOf(r);
                return (
                  <button
                    key={`${r.type}-${r.id}`}
                    role="option"
                    aria-selected={flatIdx === activeIndex}
                    onClick={() => go(r.href)}
                    className="ac-w-full"
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                      textAlign: "left",
                      padding: "8px 10px",
                      borderRadius: 6,
                      border: "none",
                      background: flatIdx === activeIndex ? "var(--ac-bg-surface-hover)" : "transparent",
                    }}
                    onMouseDown={(e) => e.preventDefault()}
                    onMouseEnter={() => setActiveIndex(flatIdx)}
                  >
                    <span>{r.title}</span>
                    <span className="ac-text-sm ac-text-muted">{r.subtitle}</span>
                  </button>
                );
              })}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
