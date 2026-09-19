/** Dispatch a plugin by a name chosen at runtime. Intentionally unresolved. */
export function dispatchPlugin(plugins, name) { return plugins[name](); }
