import { useState } from 'react';
import { ChevronDown, ChevronRight, Folder } from 'lucide-react';

export function FileTree({ files, selected, onOpen }: { files: string[]; selected?: string; onOpen: (path: string) => void }) {
  const [closed, setClosed] = useState(new Set<string>());
  function branch(prefix: string, depth: number) {
    const children = [...new Set(files.filter(f => f.startsWith(prefix)).map(f => f.slice(prefix.length).split('/')[0]))].sort((a, b) => {
      const ad = files.some(f => f.startsWith(prefix + a + '/'));
      const bd = files.some(f => f.startsWith(prefix + b + '/'));
      return Number(bd) - Number(ad) || a.localeCompare(b);
    });
    return children.map(name => {
      const path = prefix + name;
      const directory = files.some(f => f.startsWith(path + '/'));
      return directory ? <div key={path}><button className="folder-row" style={{ paddingLeft: 10 + depth * 14 }} aria-expanded={!closed.has(path)} onClick={() => setClosed(previous => { const next = new Set(previous); next.has(path) ? next.delete(path) : next.add(path); return next; })}>
        {closed.has(path) ? <ChevronRight size={13}/> : <ChevronDown size={13}/>}<Folder size={15}/>{name}</button>{!closed.has(path) && branch(path + '/', depth + 1)}</div>
        : <button key={path} className={`file-row ${selected === path ? 'active' : ''}`} style={{ paddingLeft: 25 + depth * 14 }} title={path} onClick={() => onOpen(path)}><span className="js-icon">JS</span><span>{name}</span></button>;
    });
  }
  return <div className="file-tree" aria-label="Repository files">{files.length ? branch('', 0) : <p className="tree-empty">Open a repository to explore its files.</p>}</div>;
}
