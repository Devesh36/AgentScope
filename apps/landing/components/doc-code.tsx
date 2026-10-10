"use client";

import { useState } from "react";
import { Check, Copy } from "lucide-react";

export function DocCode({ title, children }: { title: string; children: string }) {
  const [status, setStatus] = useState("");
  async function copy() {
    try {
      await navigator.clipboard.writeText(children);
      setStatus("Copied.");
    } catch {
      setStatus("Select the code below to copy it.");
    }
  }
  return (
    <div className="docs-code">
      <div className="docs-code-bar">
        <span>{title}</span>
        <div><span role="status">{status}</span><button type="button" aria-label={`Copy ${title}`} onClick={copy}>{status === "Copied." ? <Check size={15} /> : <Copy size={15} />} Copy</button></div>
      </div>
      <pre><code>{children}</code></pre>
    </div>
  );
}
