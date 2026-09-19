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
run(python, ['-m', 'pip', 'install', '-c', 'requirements.lock.txt', '-e', process.env.ASTFLOW_SEMANTIC === 'off' ? '.[dev]' : '.[dev,semantic]']);
run(windows ? 'npm.cmd' : 'npm', ['ci']);
run(windows ? 'npm.cmd' : 'npm', ['run', 'build']);
run(python, ['scripts/setup_demo.py']);
if (process.env.ASTFLOW_SEMANTIC !== 'off') {
  const model = spawnSync(python, ['-m', 'backend.app.cli', 'model-download'], { cwd: root, stdio: 'inherit' });
  if (model.status !== 0) console.warn('Model download unavailable. Lexical search remains ready; retry astflow model-download later.');
}
console.log('Setup complete. Start with npm run demo.');
