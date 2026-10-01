"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { searchAll, type SearchResult, type SearchResultType } from "@/lib/mock/search";
import { useSession } from "@/lib/auth/SessionContext";
import { assetsApi } from "@/lib/api/assets";
import { workOrdersApi } from "@/lib/api/workOrders";
import { LIVE_GROUP_LABEL, LIVE_GROUP_ORDER, assetResults, workOrderResults, type LiveSearchResult } from "@/lib/search/live";

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

  const { isDemo, accessToken } = useSession();
  const [liveResults, setLiveResults] = useState<LiveSearchResult[]>([]);

  // Demo sessions search the bundled sample data; live sessions search only the organization's own records via the API.
  useEffect(() => {
    if (isDemo) return;
    const q = query.trim();
    if (!q || !accessToken) {
      setLiveResults([]);
      return;
    }
    let cancelled = false;
    const timer = setTimeout(async () => {
      const [assets, orders] = await Promise.allSettled([
        assetsApi.listAssets(accessToken, { search: q }),
        workOrdersApi.list(accessToken, { search: q, limit: 10 }),
      ]);
      if (cancelled) return;
      setLiveResults([
        ...(assets.status === "fulfilled" ? assetResults(assets.value) : []),
        ...(orders.status === "fulfilled" ? workOrderResults(orders.value) : []),
      ]);
    }, 250);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [query, isDemo, accessToken]);

  const demoResults = useMemo(() => (isDemo ? searchAll(query) : []), [query, isDemo]);
  const groups = useMemo<Array<{ type: string; label: string; items: Array<SearchResult | LiveSearchResult> }>>(() => {
    if (isDemo) {
      return groupResults(demoResults).map((g) => ({
        type: g.type,
        label: g.type === "WorkOrder" ? "Work Orders" : g.type === "PurchaseOrder" ? "Purchase Orders" : `${g.type}s`,
        items: g.items,
      }));
    }
    return LIVE_GROUP_ORDER.map((type) => ({
      type,
      label: LIVE_GROUP_LABEL[type],
      items: liveResults.filter((r) => r.type === type).slice(0, MAX_PER_GROUP),
    })).filter((g) => g.items.length > 0);
  }, [isDemo, demoResults, liveResults]);
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
                {group.label}
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
