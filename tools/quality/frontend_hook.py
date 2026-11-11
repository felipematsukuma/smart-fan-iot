from check import npm

for name in ("lint", "typecheck", "format:check"):
    npm("run", name)
