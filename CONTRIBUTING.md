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
npm run package   # → manim-dock-0.2.3.vsix (gitignored)
```

1. **GitHub Release (fastest public download)**  
   Push `main`, tag `v0.2.3`, attach the `.vsix`. Users: Extensions → Install from VSIX, or Cursor/VS Code can install from the release URL.

2. **Open VSX (Cursor / VSCodium friendly)**  
   Create a publisher at [open-vsx.org](https://open-vsx.org/), then:
   ```bash
   npx ovsx publish manim-dock-0.2.3.vsix -p <OPEN_VSX_TOKEN>
   ```

3. **VS Code Marketplace (largest reach)**  
   - Create a [Visual Studio Marketplace publisher](https://marketplace.visualstudio.com/manage) (Azure DevOps org + PAT with Marketplace scope).  
   - Ensure `package.json` `publisher` matches that publisher id (currently `manim-dock`).  
   - Then:
   ```bash
   npx vsce login manim-dock
   npx vsce publish
   ```
   Or publish a built file: `npx vsce publish --packagePath manim-dock-0.2.3.vsix`

Marketplace and Open VSX both need a **one-time human account**; the repo cannot finish that step alone.
