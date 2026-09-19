/** Analyze an in-memory snapshot. Never load a target tsconfig or execute target code. */
import ts from 'typescript';
import path from 'node:path';

let input = '';
for await (const piece of process.stdin) input += piece;
const { files } = JSON.parse(input);
const base = '/__astflow_snapshot__/';
const normalize = p => p.replaceAll('\\', '/');
const absolute = p => base + p;
const relative = p => normalize(p).slice(base.length);
const names = Object.keys(files).map(absolute);
const options = { allowJs: true, checkJs: true, noEmit: true, noLib: true,
  target: ts.ScriptTarget.ESNext, module: ts.ModuleKind.ESNext, jsx: ts.JsxEmit.Preserve };
const host = ts.createCompilerHost(options);
host.fileExists = file => Object.hasOwn(files, relative(file));
host.readFile = file => files[relative(file)];
host.getSourceFile = (file, languageVersion) => {
  const text = files[relative(file)];
  return text === undefined ? undefined : ts.createSourceFile(file, text, languageVersion, true);
};
host.getCurrentDirectory = () => base;
host.resolveModuleNames = (modules, containingFile) => modules.map(module => {
  if (!module.startsWith('.')) return undefined;
  const root = path.posix.normalize(path.posix.join(path.posix.dirname(normalize(containingFile)), module));
  for (const candidate of [root, root + '.js', root + '.mjs', root + '.cjs', root + '.jsx', root + '/index.js']) {
    if (host.fileExists(candidate)) return { resolvedFileName: candidate, extension: ts.Extension.Js };
  }
  return undefined;
});
const program = ts.createProgram(names, options, host);
const checker = program.getTypeChecker();
const calls = [];
const byte = (text, pos) => Buffer.byteLength(text.slice(0, pos), 'utf8');
for (const file of program.getSourceFiles()) {
  if (!Object.hasOwn(files, relative(file.fileName))) continue;
  const visit = node => {
    if (ts.isCallExpression(node) && !ts.isElementAccessExpression(node.expression)) {
      const location = ts.isPropertyAccessExpression(node.expression) ? node.expression.name : node.expression;
      let symbol = checker.getSymbolAtLocation(location);
      if (symbol && (symbol.flags & ts.SymbolFlags.Alias)) symbol = checker.getAliasedSymbol(symbol);
      const declarations = symbol?.getDeclarations() ?? [];
      if (declarations.length === 1) {
        let declaration = declarations[0];
        const callable = ts.isFunctionDeclaration(declaration) || ts.isMethodDeclaration(declaration) ||
          ((ts.isVariableDeclaration(declaration) || ts.isPropertyDeclaration(declaration)) && declaration.initializer &&
           (ts.isArrowFunction(declaration.initializer) || ts.isFunctionExpression(declaration.initializer)));
        const targetFile = declaration.getSourceFile();
        if (callable && Object.hasOwn(files, relative(targetFile.fileName))) {
          const start = node.getStart(file), end = node.getEnd();
          calls.push({ call_file: relative(file.fileName), call_line: file.getLineAndCharacterOfPosition(start).line + 1,
            call_end_line: file.getLineAndCharacterOfPosition(end).line + 1,
            call_start_byte: byte(file.text, start), call_end_byte: byte(file.text, end), expression: node.getText(file),
            target_file: relative(targetFile.fileName), target_start_byte: byte(targetFile.text, (declaration.name ?? declaration).getStart(targetFile)),
            target_name: symbol.getName(), confidence: 'LANGUAGE_SERVICE_VERIFIED' });
        }
      }
    }
    ts.forEachChild(node, visit);
  };
  visit(file);
}
process.stdout.write(JSON.stringify({ calls }));
