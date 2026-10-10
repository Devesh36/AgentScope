// Preloaded only in applications launched by agentscope watch/run.
// Metadata only: no prompt, output text, tool arguments, headers or API keys.
const fs = require('node:fs');
const { randomUUID, randomBytes } = require('node:crypto');
const endpoint = process.env.AGENTSCOPE_WATCH_URL;
const originalFetch = globalThis.fetch;
let origin;
try { origin = new URL(endpoint); } catch { /* missing or invalid monitoring config */ }

if (origin && originalFetch && origin.hostname === '127.0.0.1' && origin.protocol === 'http:' && !origin.username && !origin.password) {
  const queue = [];
  const active = new Set();
  let sending = false;
  let key;
  let dropped = 0;
  try { key = fs.readFileSync(process.env.AGENTSCOPE_WATCH_KEY_FILE, 'utf8').trim(); } catch { /* fail open */ }
  const agent = process.env.AGENTSCOPE_WATCH_AGENT_ID;
  const enqueue = event => { if (queue.length < 1000) queue.push(event); else dropped++; };
  const flush = async () => {
    if (sending || !queue.length || !key) return;
    sending = true;
    try {
      while (queue.length) {
        const batch = queue.splice(0, 50);
        let delivered = false;
        for (let attempt = 0; attempt < 3; attempt++) {
          try {
            const response = await originalFetch(`${endpoint}/api/v1/telemetry/events`, {
              method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${key}` },
              body: JSON.stringify({ events: batch }), signal: AbortSignal.timeout(1500), redirect: 'error',
            });
            await response.arrayBuffer();
            if (response.ok) { delivered = true; break; }
          } catch { /* telemetry failure must not interrupt the application */ }
        }
        if (!delivered) dropped += batch.length;
      }
    } finally { sending = false; }
  };
  const timer = setInterval(flush, 250);
  timer.unref();

  class Call {
    constructor(provider, operation, model) {
      this.provider = provider;
      this.operation = operation;
      this.model = typeof model === 'string' ? model.slice(0, 100) : null;
      this.usage = {};
      this.finished = false;
      this.root = {
        agent_id: agent, run_id: randomUUID(), trace_id: randomBytes(16).toString('hex'),
        span_id: randomBytes(8).toString('hex'), parent_span_id: null, kind: 'agent',
        name: `${provider}.${operation}`, run_name: `${provider}.${operation}`, started_at: new Date().toISOString(),
      };
      this.llm = { ...this.root, kind: 'llm', span_id: randomBytes(8).toString('hex'), parent_span_id: this.root.span_id };
      active.add(this);
      this.emit(this.root, 'running');
      this.emit(this.llm, 'running');
    }
    emit(event, status, ended = null, error = null) {
      const llm = event.kind === 'llm';
      enqueue({ ...event, event_id: randomUUID(), status, ended_at: ended, error,
        model: llm ? this.model : null, input_tokens: llm ? (this.usage.input_tokens || 0) : 0,
        output_tokens: llm ? (this.usage.output_tokens || 0) : 0,
        attributes: llm ? { provider: this.provider, capture: 'automatic', usage_observed: Number.isInteger(this.usage.input_tokens) && Number.isInteger(this.usage.output_tokens) } : { capture: 'automatic' },
      });
    }
    observe(value) {
      if (!value || typeof value !== 'object') return;
      if (value.type === 'error' || value.type === 'response.failed' || value.error) this.finish('failed', 'ProviderError');
      const message = value.message || value.response || value;
      if (typeof message.model === 'string') this.model = message.model.slice(0, 100);
      const usage = message.usage || value.usage;
      if (!usage) return;
      for (const [target, names] of [['input_tokens', ['input_tokens', 'prompt_tokens']], ['output_tokens', ['output_tokens', 'completion_tokens']]]) {
        for (const name of names) {
          if (Number.isInteger(usage[name]) && usage[name] >= 0 && usage[name] <= 1e9) {
            this.usage[target] = usage[name]; break;
          }
        }
      }
    }
    finish(status = 'completed', error = null) {
      if (this.finished) return;
      this.finished = true;
      active.delete(this);
      const ended = new Date().toISOString();
      this.emit(this.llm, status, ended, error);
      this.emit(this.root, status, ended, error);
    }
  }

  globalThis.fetch = async function monitoredFetch(input, options = {}) {
    let call;
    try {
      const url = new URL(typeof input === 'string' || input instanceof URL ? input : input.url);
      const match = url.pathname.match(/\/(chat\/completions|responses|messages)\/?$/);
      const method = options.method || input.method || 'GET';
      if (key && agent && match && method.toUpperCase() === 'POST') {
        let body = options.body;
        if (body === undefined && input instanceof Request) body = await input.clone().text();
        let model;
        if (typeof body === 'string' && body.length <= 2 * 1024 * 1024) {
          try { model = JSON.parse(body).model; } catch { /* optional metadata */ }
        }
        call = new Call(match[1] === 'messages' ? 'anthropic' : 'openai', match[1].replace('/', '.'), model);
      }
    } catch { /* unsupported request; preserve native fetch semantics */ }
    let response;
    try { response = await originalFetch(input, options); }
    catch (error) { if (call) call.finish('failed', error.name || 'Error'); throw error; }
    if (!call) return response;
    if (!response.ok) { call.finish('failed', `HTTP${response.status}`); return response; }
    if (!response.headers.get('content-type')?.includes('text/event-stream')) {
      // A clone leaves the response consumed by the provider SDK intact.
      response.clone().json().then(value => { call.observe(value); call.finish(); }).catch(() => call.finish('failed', 'InvalidResponseJSON'));
      return response;
    }
    // Observe chunks as the app consumes them; cancellation reaches the original
    // provider stream rather than leaving a background reader consuming tokens.
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    const inspect = bytes => {
      buffer += decoder.decode(bytes, { stream: true });
      const lines = buffer.split(/\r?\n/);
      buffer = lines.pop();
      if (buffer.length > 1024 * 1024) buffer = '';
      for (const line of lines) {
        if (!line.startsWith('data:')) continue;
        const payload = line.slice(5).trim();
        if (!payload || payload === '[DONE]') continue;
        try { call.observe(JSON.parse(payload)); } catch { /* optional metadata */ }
      }
    };
    const body = new ReadableStream({
      async pull(controller) {
        try {
          const { value, done } = await reader.read();
          if (done) { call.finish(); controller.close(); }
          else { inspect(value); controller.enqueue(value); }
        } catch (error) { call.finish(error.name === 'AbortError' ? 'cancelled' : 'failed', error.name || 'Error'); controller.error(error); }
      },
      async cancel(reason) { call.finish('cancelled'); await reader.cancel(reason); },
    });
    const monitored = new Response(body, { status: response.status, statusText: response.statusText, headers: response.headers });
    for (const property of ['url', 'redirected', 'type']) Object.defineProperty(monitored, property, { value: response[property] });
    return monitored;
  };

  process.on('beforeExit', () => {
    for (const call of active) call.finish('cancelled');
    if (queue.length && key) void flush();
  });
  process.on('exit', () => {
    clearInterval(timer);
    if (dropped || queue.length) console.error(`AgentScope: ${dropped + queue.length} telemetry events were dropped; check local API availability.`);
  });
}
