"use client";
import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Copy, RotateCcw, Search } from "lucide-react";
import { PAGE_SIZE, readExplorerFilters, updateView, viewLink } from "@/lib/explorer-filters";
import { useWorkspace } from "./workspace";
import { Button } from "./ui/button";

export function useExplorerFilters(kind: "runs" | "incidents") {
  const params = useSearchParams();
  const { project } = useWorkspace();
  const [searchKey, setSearchKey] = useState(0);
  const filters = readExplorerFilters(params, kind);
  function update(values: Record<string, string | null>, replace = false) {
    updateView({ project, page: null, ...values }, replace);
  }
  return {
    ...filters,
    searchKey,
    update,
    setOffset: (offset: number) => update({ page: offset ? String(offset / PAGE_SIZE + 1) : null }),
    reset: () => {
      setSearchKey((value) => value + 1);
      update({ q: null, status: null, severity: null, sort: null });
    },
  };
}

export function ExplorerSearch({ value, onChange, kind }: { value: string; onChange: (value: string) => void; kind: "runs" | "incidents" }) {
  const [draft, setDraft] = useState(value);
  const revision = useSearchParams().toString();
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  useEffect(() => {
    setDraft(value);
    clearTimeout(timer.current);
  }, [value, revision]);
  useEffect(() => () => clearTimeout(timer.current), []);
  return (
    <div className="search-input">
      <Search size={15} aria-hidden="true" />
      <input
        aria-label={`Search ${kind}`}
        placeholder={kind === "runs" ? "Search run, agent, or execution ID…" : "Search incidents or affected agents…"}
        maxLength={200}
        value={draft}
        onChange={(event) => {
          const next = event.target.value;
          setDraft(next);
          clearTimeout(timer.current);
          timer.current = setTimeout(() => onChange(next), 300);
        }}
        onKeyDown={(event) => {
          if (event.key === "Enter") {
            clearTimeout(timer.current);
            onChange(draft);
          }
        }}
      />
    </div>
  );
}

export function ExplorerActions({ kind, reset }: { kind: "runs" | "incidents"; reset: () => void }) {
  const { project, hours, source, notify } = useWorkspace();
  return (
    <>
      <Button onClick={reset}><RotateCcw size={14} />Reset filters</Button>
      <Button onClick={async () => {
        try {
          await navigator.clipboard.writeText(viewLink(window.location.href, project, hours, source, kind));
          notify("View link copied. It opens this project and these filters.");
        } catch {
          notify("Clipboard unavailable. Copy the view URL from your browser address bar.", true);
        }
      }}><Copy size={14} />Copy view link</Button>
    </>
  );
}
