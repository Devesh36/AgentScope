const assert = require('node:assert/strict');
const { createRequire } = require('node:module');
const requireProvider = createRequire(process.env.WATCH_NODE_PACKAGE);
const OpenAI = requireProvider('openai').default;
const Anthropic = requireProvider('@anthropic-ai/sdk').default;
const origin = process.env.WATCH_MOCK_ORIGIN;
const options = { model: 'gpt-4o-mini', messages: [{ role: 'user', content: 'private-prompt-sentinel' }] };
const client = new OpenAI({ apiKey: 'mock-provider-key', baseURL: origin + '/v1', maxRetries: 0 });
const claude = new Anthropic({ apiKey: 'mock-provider-key', baseURL: origin, maxRetries: 0 });

async function run() {
  assert.equal((await client.chat.completions.create(options)).choices[0].message.content, 'private-answer-sentinel');
  const chat = await client.chat.completions.create({ ...options, stream: true, stream_options: { include_usage: true } });
  let final;
  for await (const chunk of chat) final = chunk;
  assert.equal(final.usage.completion_tokens, 7);
  assert.equal((await client.responses.create({ model: 'gpt-4o-mini', input: 'private-prompt-sentinel' })).usage.input_tokens, 13);
  const responses = await client.responses.create({ model: 'gpt-4o-mini', input: 'private-prompt-sentinel', stream: true });
  for await (const chunk of responses) final = chunk;
  assert.equal(final.type, 'response.completed');
  const anthropic = { model: 'claude-test', max_tokens: 10, messages: options.messages };
  assert.equal((await claude.messages.create(anthropic)).usage.input_tokens, 5);
  for await (const chunk of await claude.messages.create({ ...anthropic, stream: true })) final = chunk;
  assert.equal(final.type, 'message_stop');
  await assert.rejects(client.chat.completions.create({ ...options, model: 'fail' }));
  assert.equal((await fetch(origin + '/health')).status, 200);
}
run().catch(() => { console.error('Node provider fixture failed.'); process.exitCode = 1; });
