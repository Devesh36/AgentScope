"use client";

import { useState } from "react";
import { Check, Copy, Terminal } from "lucide-react";

const commands = {
  uv: 'uv tool install "git+https://github.com/Devesh36/AgentScope.git@main"',
  Homebrew: "brew tap Devesh36/agentscope https://github.com/Devesh36/AgentScope.git\nbrew install Devesh36/agentscope/agentscope",
};

export function InstallCommand() {
  const [method, setMethod] = useState<keyof typeof commands>("uv");
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState(false);
  async function copy() {
    try {
      await navigator.clipboard.writeText(commands[method]);
      setCopied(true);
      setError(false);
    } catch {
      setError(true);
    }
  }
  return (
    <div className="landing-install">
      <div className="landing-install-bar">
        <div role="tablist" aria-label="Installation method">
          {Object.keys(commands).map((name) => (
            <button key={name} id={`install-${name}`} role="tab" aria-selected={method === name} aria-controls="install-command" onClick={() => { setMethod(name as keyof typeof commands); setCopied(false); setError(false); }}>{name}</button>
          ))}
        </div>
        <span><Terminal size={13} /> Terminal</span>
      </div>
      <div role="tabpanel" id="install-command" aria-labelledby={`install-${method}`} className="landing-install-code">
        <code>{commands[method]}</code>
        <button aria-label="Copy install command" onClick={copy}>{copied ? <Check size={16} /> : <Copy size={16} />}</button>
      </div>
      <p role="status">{error ? "Clipboard unavailable. Select and copy the command above." : copied ? "Copied install command." : method === "uv" ? "Python 3.12+ · installed from source with uv" : "Custom Homebrew tap · Python installed as a dependency"}</p>
    </div>
  );
}
