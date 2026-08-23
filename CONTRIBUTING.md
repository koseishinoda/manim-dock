# Contributing to Manim Dock

Thanks for helping. Keep the [invasion test](docs/invasion-test.md) green.

## Dev setup

1. Python sidecar: `cd python && python3 -m venv .venv && source .venv/bin/activate && pip install -e ".[dev]"`
2. Extension: `npm install && npm run compile`
3. Launch **Run Manim Dock Extension** from the debug panel
4. Optional package check: `npm run package` (must include `python/manim_dock`, `media/stageTimeline.js`, `templates/`, `snippets/`)

## PR checklist

- [ ] Plain ManimCE examples still run without the extension
- [ ] No required Dock scene base class
- [ ] Tests updated for parser/patch changes
- [ ] UX degrade path when parse is incomplete

## Public deploy (three paths)

Build first:

```bash
npm run package   # → manim-dock-0.2.6.vsix (gitignored)
```

Publisher id in `package.json` is **`manim-dock`** — use the **same** name on both stores.

### 1. GitHub Release

https://github.com/koseishinoda/manim-dock/releases — Install from VSIX.

### 2. Open VSX (Cursor Extensions search)

1. Create / sign in: [open-vsx.org](https://open-vsx.org/) (GitHub login)
2. Profile → connect Eclipse account → **sign Open VSX Publisher Agreement**
3. [Access Tokens](https://open-vsx.org/user-settings/tokens) → Generate New Token → copy it
4. One-time namespace (matches `publisher`):
   ```bash
   npx ovsx create-namespace manim-dock -p "$OVSX_PAT"
   ```
5. Publish:
   ```bash
   export OVSX_PAT='…'   # paste token; do not commit
   npx ovsx publish manim-dock-0.2.6.vsix -p "$OVSX_PAT"
   ```
6. Check: https://open-vsx.org/extension/manim-dock/manim-dock

### 3. VS Code Marketplace

1. Create publisher **`manim-dock`**: [marketplace.visualstudio.com/manage](https://marketplace.visualstudio.com/manage)  
   (needs a Microsoft / Azure DevOps account)
2. Create Azure DevOps PAT with **Marketplace → Acquire, Publish**  
   https://dev.azure.com → User settings → Personal access tokens
3. Publish:
   ```bash
   export VSCE_PAT='…'   # paste PAT; do not commit
   npx vsce publish --packagePath manim-dock-0.2.6.vsix -p "$VSCE_PAT"
   ```
4. Check: https://marketplace.visualstudio.com/items?itemName=manim-dock.manim-dock

Do **not** put tokens in the repo or chat. After both succeed, Cursor (Open VSX) and VS Code (Marketplace) can install from Extensions search.
