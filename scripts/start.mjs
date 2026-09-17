import { spawn, spawnSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const python = path.join(root, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
if (!existsSync(python) || !existsSync(path.join(root, 'frontend/dist/index.html'))) {
  console.error('Run npm run setup first.'); process.exit(1);
}
console.log('\nPreparing ASTFLOW at http://127.0.0.1:8000\n');
const server = spawn(python, ['-m', 'backend.app.cli', 'demo'], { cwd: root, stdio: 'inherit' });
process.on('SIGINT', () => server.kill('SIGINT'));
process.on('SIGTERM', () => server.kill('SIGTERM'));
server.on('exit', code => process.exit(code ?? 0));
