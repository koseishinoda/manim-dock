import { spawn } from "child_process";
import * as fs from "fs";
import * as path from "path";
import * as vscode from "vscode";

export interface SourceRange {
  start_line: number;
  end_line: number;
}

export interface OutlineEvent {
  kind: string;
  label: string;
  range: SourceRange;
  targets?: string[];
}

export interface OutlineMethod {
  name: string;
  range: SourceRange;
  events: OutlineEvent[];
}

export interface OutlineScene {
  name: string;
  bases: string[];
  range: SourceRange;
  methods: OutlineMethod[];
}

export interface FileOutline {
  path: string;
  scenes: OutlineScene[];
  errors: string[];
}


export interface RenderResult {
  ok: boolean;
  output_path: string | null;
  command: string[];
  cwd: string;
  returncode: number | null;
  log_tail: string;
  error: string | null;
}

export interface SceneOutput {
  scene: string;
  path: string | null;
}

export interface MultiSceneRenderResult {
  ok: boolean;
  outputs: SceneOutput[];
  command: string[];
  cwd: string;
  returncode: number | null;
  log_tail: string;
  error: string | null;
  quality_dir: string;
}

export interface SnapshotResult {
  ok: boolean;
  path: string;
  scene: string;
  active_until_line: number;
  quality: string;
  cache_key: string;
  cached: boolean;
  png_path: string | null;
  width: number | null;
  height: number | null;
  command: string[];
  returncode: number | null;
  log_tail: string;
  error: string | null;
  /** ``cache`` | ``inprocess`` | ``cli`` when provided by the sidecar. */
  engine?: string;
}

export interface StillGetResult {
  ok: boolean;
  path: string;
  scene: string;
  line: number;
  beat?: {
    ordinal: number;
    kind: string;
    label: string;
    source_line: number;
    section: string;
    cache_key: string;
    start_line?: number;
  } | null;
  png_path: string | null;
  width: number | null;
  height: number | null;
  cached: boolean;
  captured: boolean;
  engine: string;
  error: string | null;
  index_cached: number;
  index_total: number;
}

export interface StillIndexResult {
  ok: boolean;
  path: string;
  scene: string;
  built: number;
  skipped: number;
  cached: number;
  total: number;
  complete: boolean;
  next_ordinal: number | null;
  section: string;
  error: string | null;
  last_engine: string;
}

export interface StillIndexStatus {
  ok: boolean;
  path: string;
  scene: string;
  cached: number;
  total: number;
  complete: boolean;
  next_ordinal: number | null;
  section: string;
  error: string | null;
}


export interface TimelineEvent {
  id: string;
  kind: string;
  label: string;
  method: string;
  range: SourceRange;
  start: number;
  duration: number;
  editable: boolean;
  duration_source: string;
  note: string;
  /** Enclosing next_section label; empty before the first section. */
  section?: string;
  /** Binding names inside Write/FadeIn/… args when statically recoverable. */
  targets?: string[];
}

export interface SceneTimeline {
  path: string;
  scene: string;
  total_duration: number;
  events: TimelineEvent[];
  errors: string[];
}

export interface TimingPatchProposal {
  ok: boolean;
  path: string;
  kind: string;
  line: number;
  duration: number;
  original: string;
  proposed: string;
  diff: string;
  error: string | null;
  summary: string;
}

export interface ReorderPatchProposal {
  ok: boolean;
  path: string;
  line_a: number;
  line_b: number;
  original: string;
  proposed: string;
  diff: string;
  error: string | null;
  summary: string;
}

export interface RenderOptions {
  saveSections?: boolean;
  skipUntilSection?: string;
  /** Render only this next_section chapter (skip before and after). */
  sectionOnly?: string;
  /** When set, rewrite construct to only call this method before render. */
  method?: string;
}




export interface LibraryHelper {
  name: string;
  signature: string;
  doc: string;
  insert: string;
}

export interface ExtractProposal {
  ok: boolean;
  scene_path: string;
  library_path: string;
  method: string;
  scene_original: string;
  scene_proposed: string;
  scene_diff: string;
  library_original: string;
  library_proposed: string;
  library_diff: string;
  import_name: string;
  error: string | null;
  summary: string;
}

function sidecarRoots(extensionPath: string): string[] {
  const roots: string[] = [];
  const fromExt = path.join(extensionPath, "python");
  if (fs.existsSync(path.join(fromExt, "manim_dock"))) {
    roots.push(fs.realpathSync(fromExt));
  }
  for (const folder of vscode.workspace.workspaceFolders ?? []) {
    const fromWs = path.join(folder.uri.fsPath, "python");
    if (fs.existsSync(path.join(fromWs, "manim_dock"))) {
      roots.push(fs.realpathSync(fromWs));
    }
  }
  return [...new Set(roots)];
}

function expandPythonPath(configured: string): string {
  let resolved = configured.trim();
  if (!resolved) {
    return resolved;
  }
  const folder = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
  if (folder) {
    resolved = resolved
      .replace(/\$\{workspaceFolder\}/g, folder)
      .replace(/\$\{workspaceRoot\}/g, folder);
  }
  if (resolved.startsWith("~")) {
    const home = process.env.HOME || process.env.USERPROFILE || "";
    resolved = path.join(home, resolved.slice(1));
  }
  return resolved;
}

/** Walk up from start looking for a project .venv with Manim. */
function discoverVenvPythons(...starts: string[]): string[] {
  const found: string[] = [];
  const seen = new Set<string>();
  for (const start of starts) {
    if (!start) {
      continue;
    }
    let cur = path.resolve(start);
    for (let i = 0; i < 6; i++) {
      if (seen.has(cur)) {
        break;
      }
      seen.add(cur);
      for (const rel of [
        path.join(".venv", "bin", "python"),
        path.join("venv", "bin", "python"),
        path.join(".venv", "Scripts", "python.exe"),
        path.join("venv", "Scripts", "python.exe"),
      ]) {
        const candidate = path.join(cur, rel);
        if (fs.existsSync(candidate)) {
          found.push(candidate);
        }
      }
      const parent = path.dirname(cur);
      if (parent === cur) {
        break;
      }
      cur = parent;
    }
  }
  return found;
}

async function resolvePythonBins(extensionPath?: string): Promise<string[]> {
  // Precedence (per-project Manim tools):
  // 1. Workspace / folder manimDock.pythonPath
  // 2. .venv under current workspace folder(s) (walk-up)
  // 3. VS Code / Cursor Python extension interpreter
  // 4. User-level manimDock.pythonPath (fallback only)
  // 5. Extension-repo .venv (F5 when examples/* has no local venv)
  // 6. python3 / python
  const bins: string[] = [];
  const resource =
    vscode.window.activeTextEditor?.document.uri ??
    vscode.workspace.workspaceFolders?.[0]?.uri;
  const inspected = vscode.workspace
    .getConfiguration("manimDock", resource)
    .inspect<string>("pythonPath");

  const workspaceConfigured =
    inspected?.workspaceFolderValue?.trim() ||
    inspected?.workspaceValue?.trim() ||
    "";
  const globalConfigured = inspected?.globalValue?.trim() || "";

  const pushIfExists = (raw: string | undefined): void => {
    if (!raw?.trim()) {
      return;
    }
    const expanded = expandPythonPath(raw);
    if (expanded && fs.existsSync(expanded)) {
      bins.push(expanded);
    }
  };

  pushIfExists(workspaceConfigured);

  const workspaceRoots = (vscode.workspace.workspaceFolders ?? []).map(
    (f) => f.uri.fsPath
  );
  bins.push(...discoverVenvPythons(...workspaceRoots));

  try {
    const pythonExt = vscode.extensions.getExtension("ms-python.python");
    if (pythonExt) {
      if (!pythonExt.isActive) {
        await pythonExt.activate();
      }
      const api = pythonExt.exports as {
        settings?: {
          getExecutionDetails?: (resource?: vscode.Uri) => {
            execCommand?: string[] | undefined;
          };
        };
      };
      const details = api.settings?.getExecutionDetails?.(resource);
      const cmd = details?.execCommand?.[0];
      if (cmd) {
        bins.push(cmd);
      }
    }
  } catch {
    // ignore
  }

  pushIfExists(globalConfigured);

  if (extensionPath) {
    bins.push(...discoverVenvPythons(extensionPath));
  }

  bins.push("python3", "python");
  return [...new Set(bins.filter(Boolean))];
}

/** Parse one JSON object from sidecar stdout (must not use lastIndexOf('{')). */
function extractJsonObject<T>(stdout: string): T {
  const trimmed = stdout.trim();
  if (!trimmed) {
    throw new Error("empty stdout");
  }
  // Fast path: whole stdout is the object.
  try {
    return JSON.parse(trimmed) as T;
  } catch {
    // Fall through — maybe logs preceded the JSON.
  }
  const start = trimmed.indexOf("{");
  if (start < 0) {
    throw new Error("no JSON object found in stdout");
  }
  let depth = 0;
  let inString = false;
  let escape = false;
  for (let i = start; i < trimmed.length; i++) {
    const ch = trimmed[i];
    if (inString) {
      if (escape) {
        escape = false;
      } else if (ch === "\\") {
        escape = true;
      } else if (ch === '"') {
        inString = false;
      }
      continue;
    }
    if (ch === '"') {
      inString = true;
      continue;
    }
    if (ch === "{") {
      depth += 1;
    } else if (ch === "}") {
      depth -= 1;
      if (depth === 0) {
        return JSON.parse(trimmed.slice(start, i + 1)) as T;
      }
    }
  }
  throw new Error("unterminated JSON object in stdout");
}

/** Drop huge env values so spawn argv+env stays under Linux ARG_MAX. */
const MAX_ENV_VALUE_BYTES = 8 * 1024;

function sidecarChildEnv(extra?: NodeJS.ProcessEnv): NodeJS.ProcessEnv {
  const out: NodeJS.ProcessEnv = {};
  for (const [key, value] of Object.entries(process.env)) {
    if (value === undefined) {
      continue;
    }
    if (Buffer.byteLength(value, "utf8") > MAX_ENV_VALUE_BYTES) {
      continue;
    }
    out[key] = value;
  }
  if (extra) {
    for (const [key, value] of Object.entries(extra)) {
      if (value === undefined) {
        continue;
      }
      out[key] = value;
    }
  }
  return out;
}

function runPythonJson<T>(
  pythonPath: string,
  args: string[],
  options?: {
    timeoutMs?: number;
    onLog?: (chunk: string) => void;
    cwd?: string;
    env?: NodeJS.ProcessEnv;
    /** JSON (or other) payload — never put large source in argv. */
    stdin?: string;
  }
): Promise<T> {
  return new Promise((resolve, reject) => {
    const child = spawn(pythonPath, args, {
      cwd: options?.cwd,
      env: sidecarChildEnv(options?.env),
    });
    let stdout = "";
    let stderr = "";
    const timer =
      options?.timeoutMs && options.timeoutMs > 0
        ? setTimeout(() => {
            child.kill("SIGTERM");
            reject(new Error(`sidecar timed out after ${options.timeoutMs}ms`));
          }, options.timeoutMs)
        : undefined;

    child.stdout.on("data", (chunk: Buffer) => {
      const text = chunk.toString();
      stdout += text;
      options?.onLog?.(text);
    });
    child.stderr.on("data", (chunk: Buffer) => {
      const text = chunk.toString();
      stderr += text;
      options?.onLog?.(text);
    });
    child.on("error", (err) => {
      if (timer) {
        clearTimeout(timer);
      }
      reject(err);
    });
    child.on("close", (code) => {
      if (timer) {
        clearTimeout(timer);
      }
      if (!stdout.trim()) {
        reject(
          new Error(
            stderr.trim() ||
              `no JSON from ${pythonPath} ${args.join(" ")} (exit ${code ?? "?"})`
          )
        );
        return;
      }
      try {
        resolve(extractJsonObject<T>(stdout));
      } catch (err) {
        reject(
          new Error(
            `Bad JSON from sidecar: ${String(err)}\nSTDOUT:\n${stdout}\nSTDERR:\n${stderr}`
          )
        );
      }
    });

    if (options?.stdin !== undefined) {
      child.stdin.write(options.stdin, "utf8");
    }
    child.stdin.end();
  });
}

/** Inline runner: injects sys.path so we don't depend on ambient PYTHONPATH. */
function outlineInlineCode(pythonRoot: string, filePath: string): string {
  return `
import json, sys
sys.path.insert(0, ${JSON.stringify(pythonRoot)})
from manim_dock.outline import parse_file
print(json.dumps(parse_file(${JSON.stringify(filePath)}).to_dict()))
`.trim();
}

function renderInlineCode(
  pythonRoot: string,
  filePath: string,
  sceneName: string,
  quality: string,
  opts?: RenderOptions
): string {
  const saveSections = opts?.saveSections === true;
  const skipUntil =
    opts?.skipUntilSection !== undefined && opts.skipUntilSection !== ""
      ? JSON.stringify(opts.skipUntilSection)
      : "None";
  const sectionOnly =
    opts?.sectionOnly !== undefined && opts.sectionOnly !== ""
      ? JSON.stringify(opts.sectionOnly)
      : "None";
  const method =
    opts?.method !== undefined && opts.method !== ""
      ? JSON.stringify(opts.method)
      : "None";
  return `
import json, sys
sys.path.insert(0, ${JSON.stringify(pythonRoot)})
from manim_dock.render import render_scene
print(json.dumps(render_scene(
    ${JSON.stringify(filePath)},
    ${JSON.stringify(sceneName)},
    quality=${JSON.stringify(quality)},
    save_sections=${saveSections ? "True" : "False"},
    skip_until_section=${skipUntil},
    section_only=${sectionOnly},
    method=${method},
).to_dict()))
`.trim();
}

function renderScenesInlineCode(pythonRoot: string): string {
  return `
import json, sys
sys.path.insert(0, ${JSON.stringify(pythonRoot)})
from manim_dock.render import render_scenes
p = json.load(sys.stdin)
print(json.dumps(render_scenes(
    p["file_path"],
    list(p.get("scene_names") or []),
    quality=p.get("quality", "l"),
    manim_cmd=[sys.executable, "-m", "manim"],
    timeout=p.get("timeout"),
).to_dict()))
`.trim();
}

/** Tiny -c stub: params (incl. large source) arrive as JSON on stdin. */
function snapshotAtLineInlineCode(pythonRoot: string): string {
  return `
import json, sys
sys.path.insert(0, ${JSON.stringify(pythonRoot)})
from manim_dock.snapshot import snapshot_at_line
p = json.load(sys.stdin)
print(json.dumps(snapshot_at_line(
    p["file_path"],
    p["scene_name"],
    p["active_until_line"],
    source=p.get("source"),
    quality=p.get("quality", "l"),
    timeout=p.get("timeout"),
    cache_dir=p.get("cache_dir"),
    manim_cmd=[sys.executable, "-m", "manim"],
).to_dict()))
`.trim();
}

function libraryCatalogInlineCode(
  pythonRoot: string,
  libraryPath: string
): string {
  return `
import json, sys
sys.path.insert(0, ${JSON.stringify(pythonRoot)})
from manim_dock.library_catalog import list_library_helpers
print(json.dumps({"ok": True, "helpers": list_library_helpers(${JSON.stringify(libraryPath)})}))
`.trim();
}

function proposeReorderInlineCode(pythonRoot: string): string {
  return `
import json, sys
sys.path.insert(0, ${JSON.stringify(pythonRoot)})
from manim_dock.patch_timing import propose_reorder
p = json.load(sys.stdin)
print(json.dumps(propose_reorder(
    p["source"],
    path=p["file_path"],
    line_a=p["line_a"],
    line_b=p["line_b"],
).to_dict()))
`.trim();
}

function proposeSectionReorderInlineCode(pythonRoot: string): string {
  return `
import json, sys
sys.path.insert(0, ${JSON.stringify(pythonRoot)})
from manim_dock.patch_timing import propose_section_reorder
p = json.load(sys.stdin)
print(json.dumps(propose_section_reorder(
    p["source"],
    path=p["file_path"],
    line_a=p["line_a"],
    line_b=p["line_b"],
).to_dict()))
`.trim();
}

function timelineInlineCode(pythonRoot: string): string {
  return `
import json, sys
sys.path.insert(0, ${JSON.stringify(pythonRoot)})
from manim_dock.timeline import parse_file_timeline, parse_scene_timeline
p = json.load(sys.stdin)
src = p.get("source")
if src is None:
    print(json.dumps(parse_file_timeline(p["file_path"], p["scene_name"]).to_dict()))
else:
    print(json.dumps(parse_scene_timeline(src, p["file_path"], p["scene_name"]).to_dict()))
`.trim();
}

function proposeDurationInlineCode(pythonRoot: string): string {
  return `
import json, sys
sys.path.insert(0, ${JSON.stringify(pythonRoot)})
from manim_dock.patch_timing import propose_duration
p = json.load(sys.stdin)
print(json.dumps(propose_duration(
    p["source"],
    path=p["file_path"],
    kind=p["kind"],
    line=p["line"],
    duration=p["duration"],
).to_dict()))
`.trim();
}

function extractMethodInlineCode(pythonRoot: string): string {
  return `
import json, sys
sys.path.insert(0, ${JSON.stringify(pythonRoot)})
from manim_dock.extract import propose_extract_method
p = json.load(sys.stdin)
print(json.dumps(propose_extract_method(
    p["source"],
    scene_path=p["file_path"],
    scene_name=p["scene_name"],
    method_name=p["method_name"],
    library_path=p["library_path"],
    library_source=p.get("library_source"),
).to_dict()))
`.trim();
}

/**
 * Long-lived ``python -m manim_dock serve`` session (warm imports for Stage).
 * Falls back to one-shot ``python -c`` when the worker is unavailable.
 */
class PersistentSidecarSession {
  private child: ReturnType<typeof spawn> | undefined;
  private stdoutBuf = "";
  private nextId = 1;
  private readonly pending = new Map<
    number,
    {
      resolve: (value: unknown) => void;
      reject: (err: Error) => void;
      timer: ReturnType<typeof setTimeout>;
    }
  >();
  private starting: Promise<void> | undefined;
  private pythonPath = "";
  private pythonRoot = "";

  async ensure(pythonPath: string, pythonRoot: string): Promise<void> {
    if (
      this.child &&
      !this.child.killed &&
      this.pythonPath === pythonPath &&
      this.pythonRoot === pythonRoot
    ) {
      return;
    }
    this.dispose();
    this.pythonPath = pythonPath;
    this.pythonRoot = pythonRoot;
    if (!this.starting) {
      this.starting = this.spawnWorker().finally(() => {
        this.starting = undefined;
      });
    }
    await this.starting;
  }

  private spawnWorker(): Promise<void> {
    return new Promise((resolve, reject) => {
      const priorPyPath = process.env.PYTHONPATH || "";
      const mergedPyPath = priorPyPath
        ? `${this.pythonRoot}${path.delimiter}${priorPyPath}`
        : this.pythonRoot;
      const child = spawn(
        this.pythonPath,
        ["-m", "manim_dock", "serve"],
        {
          env: sidecarChildEnv({
            PYTHONPATH: mergedPyPath,
            PYTHONUNBUFFERED: "1",
          }),
          stdio: ["pipe", "pipe", "pipe"],
        }
      );
      this.child = child;
      let settled = false;

      const fail = (err: Error): void => {
        if (!settled) {
          settled = true;
          reject(err);
        }
        this.failAll(err);
        this.child = undefined;
      };

      child.stdout?.on("data", (chunk: Buffer) => {
        this.stdoutBuf += chunk.toString();
        this.drainStdout();
      });
      child.stderr?.on("data", (_chunk: Buffer) => {
        // Worker progress / Manim noise — ignore for RPC framing.
      });
      child.on("error", (err) => {
        fail(err instanceof Error ? err : new Error(String(err)));
      });
      child.on("close", (code) => {
        fail(new Error(`manim_dock serve exited (${code ?? "?"})`));
      });

      // Ready when ping round-trips.
      void this.rawRequest("ping", {}, 8_000)
        .then(() => {
          if (!settled) {
            settled = true;
            resolve();
          }
        })
        .catch((err) => fail(err instanceof Error ? err : new Error(String(err))));
    });
  }

  private drainStdout(): void {
    let idx: number;
    while ((idx = this.stdoutBuf.indexOf("\n")) >= 0) {
      const line = this.stdoutBuf.slice(0, idx).trim();
      this.stdoutBuf = this.stdoutBuf.slice(idx + 1);
      if (!line) {
        continue;
      }
      let msg: {
        id?: number;
        result?: unknown;
        error?: { message?: string };
      };
      try {
        msg = JSON.parse(line) as typeof msg;
      } catch {
        continue;
      }
      if (typeof msg.id !== "number") {
        continue;
      }
      const pending = this.pending.get(msg.id);
      if (!pending) {
        continue;
      }
      clearTimeout(pending.timer);
      this.pending.delete(msg.id);
      if (msg.error) {
        pending.reject(new Error(msg.error.message || "sidecar error"));
      } else {
        pending.resolve(msg.result);
      }
    }
  }

  private failAll(err: Error): void {
    for (const [, p] of this.pending) {
      clearTimeout(p.timer);
      p.reject(err);
    }
    this.pending.clear();
  }

  private rawRequest(
    method: string,
    params: Record<string, unknown>,
    timeoutMs: number
  ): Promise<unknown> {
    const child = this.child;
    if (!child?.stdin) {
      return Promise.reject(new Error("sidecar worker not running"));
    }
    const id = this.nextId++;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error(`sidecar RPC timed out after ${timeoutMs}ms (${method})`));
      }, timeoutMs);
      this.pending.set(id, { resolve, reject, timer });
      child.stdin!.write(
        `${JSON.stringify({ id, method, params })}\n`,
        "utf8"
      );
    });
  }

  async request<T>(
    method: string,
    params: Record<string, unknown>,
    timeoutMs: number
  ): Promise<T> {
    return (await this.rawRequest(method, params, timeoutMs)) as T;
  }

  dispose(): void {
    this.failAll(new Error("sidecar worker disposed"));
    if (this.child) {
      this.child.removeAllListeners();
      this.child.kill("SIGTERM");
      this.child = undefined;
    }
    this.stdoutBuf = "";
  }
}

export class SidecarClient {
  private readonly worker = new PersistentSidecarSession();

  constructor(private readonly extensionPath: string) {}

  getExtensionPath(): string {
    return this.extensionPath;
  }

  getRoots(): string[] {
    return sidecarRoots(this.extensionPath);
  }

  dispose(): void {
    this.worker.dispose();
  }

  /** Kill the warm worker (e.g. abort a blocking still-index beat). */
  disposeWorker(): void {
    this.worker.dispose();
  }

  /** Warm-worker JSON-RPC with one-shot fallback for long Stage work. */
  private async callWorker<T>(
    method: string,
    params: Record<string, unknown>,
    timeoutMs: number
  ): Promise<T> {
    const roots = this.getRoots();
    if (!roots.length) {
      throw new Error(`python/manim_dock not found under ${this.extensionPath}`);
    }
    const bins = await resolvePythonBins(this.extensionPath);
    const errors: string[] = [];
    for (const root of roots) {
      for (const bin of bins) {
        try {
          await this.worker.ensure(bin, root);
          return await this.worker.request<T>(method, params, timeoutMs);
        } catch (err) {
          errors.push(`[warm ${bin}] ${String(err)}`);
          this.worker.dispose();
        }
      }
    }
    throw new Error(`${method} failed:\n${errors.join("\n")}`);
  }

  async stillGet(
    filePath: string,
    sceneName: string,
    line: number,
    source: string | undefined,
    cacheDir: string,
    quality: string = "l",
    timeoutSec: number = 90,
    captureOnMiss: boolean = true
  ): Promise<StillGetResult> {
    const hostTimeoutMs = Math.max(15_000, (timeoutSec + 15) * 1000);
    return this.callWorker<StillGetResult>(
      "still_get",
      {
        path: filePath,
        scene: sceneName,
        line,
        source: source ?? null,
        quality,
        timeout: timeoutSec,
        cache_dir: cacheDir,
        capture_on_miss: captureOnMiss,
      },
      hostTimeoutMs
    );
  }

  async stillIndex(
    filePath: string,
    sceneName: string,
    source: string | undefined,
    cacheDir: string,
    opts?: {
      quality?: string;
      maxBeats?: number;
      preferSection?: string;
      timeoutSec?: number;
    }
  ): Promise<StillIndexResult> {
    const timeoutSec = opts?.timeoutSec ?? 180;
    const hostTimeoutMs = Math.max(30_000, (timeoutSec + 30) * 1000);
    return this.callWorker<StillIndexResult>(
      "still_index",
      {
        path: filePath,
        scene: sceneName,
        source: source ?? null,
        quality: opts?.quality ?? "l",
        cache_dir: cacheDir,
        max_beats: opts?.maxBeats ?? 1,
        prefer_section: opts?.preferSection ?? null,
        timeout: timeoutSec,
      },
      hostTimeoutMs
    );
  }

  async stillIndexStatus(
    filePath: string,
    sceneName: string,
    source: string | undefined,
    cacheDir: string,
    quality: string = "l"
  ): Promise<StillIndexStatus> {
    return this.callWorker<StillIndexStatus>(
      "still_index_status",
      {
        path: filePath,
        scene: sceneName,
        source: source ?? null,
        quality,
        cache_dir: cacheDir,
      },
      30_000
    );
  }

  async outline(filePath: string): Promise<FileOutline> {
    const roots = this.getRoots();
    if (!roots.length) {
      throw new Error(
        `python/manim_dock not found.\nextensionPath=${this.extensionPath}\nReinstall or reload the extension so the bundled python/ folder is present.`
      );
    }
    const bins = await resolvePythonBins(this.extensionPath);
    const errors: string[] = [];

    for (const root of roots) {
      for (const bin of bins) {
        try {
          return await runPythonJson<FileOutline>(bin, [
            "-c",
            outlineInlineCode(root, filePath),
          ]);
        } catch (err) {
          errors.push(`[${bin} root=${root}] ${String(err)}`);
        }
      }
    }

    throw new Error(`outline failed:\n${errors.join("\n")}`);
  }

  async snapshotAtLine(
    filePath: string,
    sceneName: string,
    activeUntilLine: number,
    source?: string,
    quality: string = "l",
    timeoutSec: number = 60,
    cacheDir?: string
  ): Promise<SnapshotResult> {
    const roots = this.getRoots();
    if (!roots.length) {
      throw new Error(`python/manim_dock not found under ${this.extensionPath}`);
    }
    const bins = await resolvePythonBins(this.extensionPath);
    const errors: string[] = [];
    // Host timeout slightly above Manim timeout so Python can return a structured error.
    const hostTimeoutMs = Math.max(15_000, (timeoutSec + 15) * 1000);
    const params = {
      path: filePath,
      scene: sceneName,
      active_until_line: activeUntilLine,
      source: source ?? null,
      quality,
      timeout: timeoutSec,
      cache_dir: cacheDir ?? null,
    };

    // Prefer warm persistent worker (keeps Manim + project imports loaded).
    for (const root of roots) {
      for (const bin of bins) {
        try {
          await this.worker.ensure(bin, root);
          return await this.worker.request<SnapshotResult>(
            "snapshot",
            params,
            hostTimeoutMs
          );
        } catch (err) {
          errors.push(`[warm ${bin}] ${String(err)}`);
          this.worker.dispose();
        }
      }
    }

    // Fallback: one-shot python -c (cold imports).
    for (const root of roots) {
      for (const bin of bins) {
        try {
          return await runPythonJson<SnapshotResult>(
            bin,
            ["-c", snapshotAtLineInlineCode(root)],
            {
              timeoutMs: hostTimeoutMs,
              stdin: JSON.stringify({
                file_path: filePath,
                scene_name: sceneName,
                active_until_line: activeUntilLine,
                source: source ?? null,
                quality,
                timeout: timeoutSec,
                cache_dir: cacheDir ?? null,
              }),
            }
          );
        } catch (err) {
          errors.push(`[${bin}] ${String(err)}`);
        }
      }
    }
    throw new Error(`snapshot failed:\n${errors.join("\n")}`);
  }

  async libraryCatalog(libraryPath: string): Promise<LibraryHelper[]> {
    const roots = this.getRoots();
    if (!roots.length) {
      throw new Error(`python/manim_dock not found under ${this.extensionPath}`);
    }
    const bins = await resolvePythonBins(this.extensionPath);
    const errors: string[] = [];
    for (const root of roots) {
      for (const bin of bins) {
        try {
          const result = await runPythonJson<{
            ok: boolean;
            helpers: LibraryHelper[];
          }>(bin, ["-c", libraryCatalogInlineCode(root, libraryPath)]);
          return result.helpers ?? [];
        } catch (err) {
          errors.push(`[${bin}] ${String(err)}`);
        }
      }
    }
    throw new Error(`library_catalog failed:\n${errors.join("\n")}`);
  }

  async proposeReorder(
    filePath: string,
    lineA: number,
    lineB: number,
    source: string
  ): Promise<ReorderPatchProposal> {
    const roots = this.getRoots();
    if (!roots.length) {
      throw new Error(`python/manim_dock not found under ${this.extensionPath}`);
    }
    const bins = await resolvePythonBins(this.extensionPath);
    const errors: string[] = [];
    for (const root of roots) {
      for (const bin of bins) {
        try {
          return await runPythonJson<ReorderPatchProposal>(bin, [
            "-c",
            proposeReorderInlineCode(root),
          ], {
            stdin: JSON.stringify({
              source,
              file_path: filePath,
              line_a: lineA,
              line_b: lineB,
            }),
          });
        } catch (err) {
          errors.push(`[${bin}] ${String(err)}`);
        }
      }
    }
    throw new Error(`propose_reorder failed:\n${errors.join("\n")}`);
  }

  async proposeSectionReorder(
    filePath: string,
    lineA: number,
    lineB: number,
    source: string
  ): Promise<ReorderPatchProposal> {
    const roots = this.getRoots();
    if (!roots.length) {
      throw new Error(`python/manim_dock not found under ${this.extensionPath}`);
    }
    const bins = await resolvePythonBins(this.extensionPath);
    const errors: string[] = [];
    for (const root of roots) {
      for (const bin of bins) {
        try {
          return await runPythonJson<ReorderPatchProposal>(bin, [
            "-c",
            proposeSectionReorderInlineCode(root),
          ], {
            stdin: JSON.stringify({
              source,
              file_path: filePath,
              line_a: lineA,
              line_b: lineB,
            }),
          });
        } catch (err) {
          errors.push(`[${bin}] ${String(err)}`);
        }
      }
    }
    throw new Error(`propose_section_reorder failed:\n${errors.join("\n")}`);
  }

  async timeline(
    filePath: string,
    sceneName: string,
    source?: string
  ): Promise<SceneTimeline> {
    const roots = this.getRoots();
    if (!roots.length) {
      throw new Error(`python/manim_dock not found under ${this.extensionPath}`);
    }
    const bins = await resolvePythonBins(this.extensionPath);
    const errors: string[] = [];
    for (const root of roots) {
      for (const bin of bins) {
        try {
          return await runPythonJson<SceneTimeline>(
            bin,
            ["-c", timelineInlineCode(root)],
            {
              timeoutMs: 30_000,
              stdin: JSON.stringify({
                file_path: filePath,
                scene_name: sceneName,
                source: source ?? null,
              }),
            }
          );
        } catch (err) {
          errors.push(`[${bin}] ${String(err)}`);
        }
      }
    }
    throw new Error(`timeline failed:\n${errors.join("\n")}`);
  }

  async proposeDuration(
    filePath: string,
    kind: string,
    line: number,
    duration: number,
    source: string
  ): Promise<TimingPatchProposal> {
    const roots = this.getRoots();
    if (!roots.length) {
      throw new Error(`python/manim_dock not found under ${this.extensionPath}`);
    }
    const bins = await resolvePythonBins(this.extensionPath);
    const errors: string[] = [];
    for (const root of roots) {
      for (const bin of bins) {
        try {
          return await runPythonJson<TimingPatchProposal>(bin, [
            "-c",
            proposeDurationInlineCode(root),
          ], {
            stdin: JSON.stringify({
              source,
              file_path: filePath,
              kind,
              line,
              duration,
            }),
          });
        } catch (err) {
          errors.push(`[${bin}] ${String(err)}`);
        }
      }
    }
    throw new Error(`propose_duration failed:\n${errors.join("\n")}`);
  }

  async extractMethod(
    filePath: string,
    sceneName: string,
    methodName: string,
    libraryPath: string,
    source: string,
    librarySource: string | null
  ): Promise<ExtractProposal> {
    const roots = this.getRoots();
    if (!roots.length) {
      throw new Error(`python/manim_dock not found under ${this.extensionPath}`);
    }
    const bins = await resolvePythonBins(this.extensionPath);
    const errors: string[] = [];
    for (const root of roots) {
      for (const bin of bins) {
        try {
          return await runPythonJson<ExtractProposal>(bin, [
            "-c",
            extractMethodInlineCode(root),
          ], {
            stdin: JSON.stringify({
              source,
              file_path: filePath,
              scene_name: sceneName,
              method_name: methodName,
              library_path: libraryPath,
              library_source: librarySource,
            }),
          });
        } catch (err) {
          errors.push(`[${bin}] ${String(err)}`);
        }
      }
    }
    throw new Error(`extract_method failed:\n${errors.join("\n")}`);
  }

  async render(
    filePath: string,
    sceneName: string,
    quality: string = "l",
    onLog?: (chunk: string) => void,
    opts?: RenderOptions
  ): Promise<RenderResult> {
    const roots = this.getRoots();
    if (!roots.length) {
      throw new Error(`python/manim_dock not found under ${this.extensionPath}`);
    }
    const bins = await resolvePythonBins(this.extensionPath);
    const errors: string[] = [];
    const timeoutMs = 15 * 60 * 1000;
    const params: Record<string, unknown> = {
      path: filePath,
      scene: sceneName,
      quality,
      save_sections: opts?.saveSections === true,
      skip_until_section: opts?.skipUntilSection || null,
      section_only: opts?.sectionOnly || null,
      method: opts?.method || null,
    };

    // Always one-shot for render. The Stage warm worker is often busy with a
    // section ladder / still_get; sharing it made ▶ QL "Render Section" appear
    // dead (RPC queued behind a long capture). Stage keeps the warm worker.
    for (const root of roots) {
      for (const bin of bins) {
        try {
          onLog?.(
            `[manim-dock] render ${sceneName}` +
              (opts?.sectionOnly ? ` section_only=${opts.sectionOnly}` : "") +
              "\n"
          );
          return await runPythonJson<RenderResult>(
            bin,
            [
              "-c",
              renderInlineCode(root, filePath, sceneName, quality, opts),
            ],
            {
              timeoutMs,
              onLog,
            }
          );
        } catch (err) {
          errors.push(`[${bin}] ${String(err)}`);
        }
      }
    }
    throw new Error(`render failed:\n${errors.join("\n")}`);
  }

  async renderScenes(
    filePath: string,
    sceneNames: string[],
    quality: string = "l",
    onLog?: (chunk: string) => void,
    timeoutSec: number = 3600
  ): Promise<MultiSceneRenderResult> {
    const roots = this.getRoots();
    if (!roots.length) {
      throw new Error(`python/manim_dock not found under ${this.extensionPath}`);
    }
    const bins = await resolvePythonBins(this.extensionPath);
    const errors: string[] = [];
    const hostTimeoutMs = Math.max(60_000, (timeoutSec + 30) * 1000);
    for (const root of roots) {
      for (const bin of bins) {
        try {
          return await runPythonJson<MultiSceneRenderResult>(
            bin,
            ["-c", renderScenesInlineCode(root)],
            {
              timeoutMs: hostTimeoutMs,
              onLog,
              stdin: JSON.stringify({
                file_path: filePath,
                scene_names: sceneNames,
                quality,
                timeout: timeoutSec,
              }),
            }
          );
        } catch (err) {
          errors.push(`[${bin}] ${String(err)}`);
        }
      }
    }
    throw new Error(`render_scenes failed:\n${errors.join("\n")}`);
  }

  async debugReport(sampleFile?: string): Promise<string> {
    const lines: string[] = [];
    lines.push(`extensionPath: ${this.extensionPath}`);
    lines.push(`roots: ${JSON.stringify(this.getRoots())}`);
    lines.push(`bins: ${JSON.stringify(await resolvePythonBins(this.extensionPath))}`);
    if (sampleFile) {
      try {
        const outline = await this.outline(sampleFile);
        lines.push(
          `outline OK: scenes=${outline.scenes.map((s) => s.name).join(",") || "(none)"} errors=${outline.errors.join(" | ") || "(none)"}`
        );
      } catch (err) {
        lines.push(`outline ERROR: ${String(err)}`);
      }
    }
    return lines.join("\n");
  }
}
