import { spawnSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const windows = process.platform === 'win32';
const python = path.join(root, '.venv', windows ? 'Scripts/python.exe' : 'bin/python');
function run(cmd, args) {
  const result = spawnSync(cmd, args, { cwd: root, stdio: 'inherit', shell: windows && cmd.endsWith('.cmd') });
  if (result.status !== 0) process.exit(result.status ?? 1);
}
if (!existsSync(python)) run(windows ? 'py' : 'python3', windows ? ['-3.12', '-m', 'venv', '.venv'] : ['-m', 'venv', '.venv']);
run(python, ['-m', 'pip', 'install', '--upgrade', 'pip>=26.2.1']);
// ASTFLOW runs on CPU. On Linux, PyPI's default torch wheel is the CUDA build (several GB of GPU libraries); take the
// CPU build, as CI and the official evaluation did. Windows and macOS wheels on PyPI are already CPU builds.
const cpuTorch = process.platform === 'linux' && !process.env.PIP_EXTRA_INDEX_URL ? ['--extra-index-url', 'https://download.pytorch.org/whl/cpu'] : [];
run(python, ['-m', 'pip', 'install', ...cpuTorch, '-c', 'requirements.lock.txt', '-e', process.env.ASTFLOW_SEMANTIC === 'off' ? '.[dev,apps]' : '.[dev,semantic,apps]']);
run(windows ? 'npm.cmd' : 'npm', ['ci']);
run(windows ? 'npm.cmd' : 'npm', ['run', 'build']);
run(python, ['scripts/setup_demo.py']);
if (process.env.ASTFLOW_SEMANTIC !== 'off') {
  const name = process.env.ASTFLOW_MODEL || 'Alibaba-NLP/gte-modernbert-base';
  console.log(`\nDownloading the search model ${name} (one time, about 0.6 GB; runs on CPU)…`);
  const model = spawnSync(python, ['-m', 'backend.app.cli', 'model-download'], { cwd: root, stdio: 'inherit' });
  if (model.status !== 0) {
    console.error(`\nSetup incomplete: the search model ${name} could not be downloaded (see the error above).\n` +
      'Check the internet connection and run npm run setup again. To use lexical-only search instead, set ASTFLOW_SEMANTIC=off.');
    process.exit(1);
  }
}
console.log('Setup complete. Start with npm run demo.');
