#!/usr/bin/env node
import { spawnSync } from 'node:child_process';

const candidates = process.env.DATADOCTOR_PYTHON
  ? [process.env.DATADOCTOR_PYTHON]
  : process.platform === 'win32' ? ['python', 'py'] : ['python3', 'python'];

let lastError = 'No Python executable could be started.';
for (const executable of candidates) {
  const args = executable === 'py' ? ['-3', '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_*.py', '-v']
    : ['-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_*.py', '-v'];
  const result = spawnSync(executable, args, { stdio: 'inherit', shell: false });
  if (result.error) {
    lastError = result.error.message;
    continue;
  }
  process.exit(result.status ?? 1);
}
process.stderr.write(`DataDoctor could not run Python tests. Set DATADOCTOR_PYTHON to your Python executable. ${lastError}\n`);
process.exit(1);
