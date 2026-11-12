import test from 'node:test';
import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import { createInterface } from 'node:readline';
import { once } from 'node:events';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { setTimeout as delay } from 'node:timers/promises';

const projectRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const entry = resolve(projectRoot, 'dist', 'index.js');
const sampleRoot = resolve(projectRoot, 'examples', 'sample-data');

function createLineQueue(readline) {
  const messages = [];
  const waiters = [];
  readline.on('line', (line) => {
    try {
      const value = JSON.parse(line);
      const waiterIndex = waiters.findIndex((waiter) => waiter.predicate(value));
      if (waiterIndex >= 0) {
        const [waiter] = waiters.splice(waiterIndex, 1);
        waiter.resolve(value);
      } else {
        messages.push(value);
      }
    } catch {
      // A non-JSON stdout line is a protocol violation; retain it for diagnostics.
      messages.push({ nonJsonLine: line });
    }
  });
  return {
    next(predicate, timeoutMs = 8000) {
      const index = messages.findIndex(predicate);
      if (index >= 0) return Promise.resolve(messages.splice(index, 1)[0]);
      return new Promise((resolvePromise, rejectPromise) => {
        const waiter = { predicate, resolve: resolvePromise, reject: rejectPromise };
        waiters.push(waiter);
        const timer = setTimeout(() => {
          const at = waiters.indexOf(waiter);
          if (at >= 0) waiters.splice(at, 1);
          rejectPromise(new Error('Timed out waiting for MCP response.'));
        }, timeoutMs);
        timer.unref?.();
      });
    }
  };
}

test('stdio MCP server initializes, lists tools, and inspects a file', async (t) => {
  const child = spawn(process.execPath, [entry, '--root', sampleRoot], {
    cwd: projectRoot,
    stdio: ['pipe', 'pipe', 'pipe'],
    env: process.env
  });
  const stdout = createInterface({ input: child.stdout });
  const queue = createLineQueue(stdout);
  let stderr = '';
  child.stderr.setEncoding('utf8');
  child.stderr.on('data', (chunk) => { stderr += chunk; });
  t.after(() => {
    stdout.close();
    child.kill();
  });

  const send = (message) => child.stdin.write(`${JSON.stringify(message)}\n`);

  send({
    jsonrpc: '2.0', id: 1, method: 'initialize',
    params: {
      protocolVersion: '2025-11-25',
      capabilities: {},
      clientInfo: { name: 'datadoctor-test', version: '0.2.0' }
    }
  });
  const initialized = await queue.next((message) => message.id === 1);
  assert.equal(initialized.error, undefined, JSON.stringify(initialized.error));
  assert.equal(initialized.result?.serverInfo?.name, 'datadoctor-mcp');

  send({ jsonrpc: '2.0', method: 'notifications/initialized' });
  send({ jsonrpc: '2.0', id: 2, method: 'tools/list', params: {} });
  const listing = await queue.next((message) => message.id === 2);
  assert.equal(listing.error, undefined);
  const names = listing.result.tools.map((tool) => tool.name);
  assert.ok(names.includes('scan_data'));
  assert.ok(names.includes('repair_data'));
  assert.ok(names.includes('profile_dataset'));
  assert.equal(names.length, 10);

  send({ jsonrpc: '2.0', id: 4, method: 'prompts/list', params: {} });
  const prompts = await queue.next((message) => message.id === 4);
  assert.equal(prompts.error, undefined);
  const promptNames = prompts.result.prompts.map((prompt) => prompt.name);
  assert.ok(promptNames.includes('audit-data-directory'));
  assert.ok(promptNames.includes('prepare-safe-repair'));
  assert.equal(promptNames.length, 3);

  send({
    jsonrpc: '2.0', id: 3, method: 'tools/call',
    params: { name: 'inspect_file', arguments: { path: resolve(sampleRoot, 'healthy.json') } }
  });
  const call = await queue.next((message) => message.id === 3);
  assert.equal(call.error, undefined);
  assert.equal(call.result?.isError, undefined);
  const text = call.result?.content?.find((item) => item.type === 'text')?.text;
  assert.ok(text, `Missing text content. stderr: ${stderr}`);
  const payload = JSON.parse(text);
  assert.equal(payload.operation, 'inspect_file');
  assert.equal(payload.result.validation.valid, true);
  assert.match(payload.result.sha256, /^[a-f0-9]{64}$/);
});
