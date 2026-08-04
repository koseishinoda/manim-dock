import { spawn } from "child_process";
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

export interface DoctorProbe {
  name: string;
  ok: boolean;
  detail: string;
}

function workspacePythonDir(extensionPath: string): string {
  return path.join(extensionPath, "python");
}

async function resolvePythonPath(extensionPath: string): Promise<string> {
  const configured = vscode.workspace
    .getConfiguration("manimDock")
    .get<string>("pythonPath")
    ?.trim();
  if (configured) {
    return configured;
  }

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
      const details = api.settings?.getExecutionDetails?.(
        vscode.window.activeTextEditor?.document.uri
      );
      const cmd = details?.execCommand?.[0];
      if (cmd) {
        return cmd;
      }
    }
  } catch {
    // Fall through to python3
  }

  return "python3";
}

function runPythonJson<T>(
  pythonPath: string,
  args: string[],
  cwd: string
): Promise<T> {
  return new Promise((resolve, reject) => {
    const child = spawn(pythonPath, args, {
      cwd,
      env: {
        ...process.env,
        PYTHONPATH: cwd + path.delimiter + (process.env.PYTHONPATH ?? ""),
      },
    });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk: Buffer) => {
      stdout += chunk.toString();
    });
    child.stderr.on("data", (chunk: Buffer) => {
      stderr += chunk.toString();
    });
    child.on("error", reject);
    child.on("close", (code) => {
      if (!stdout.trim()) {
        reject(
          new Error(
            stderr.trim() ||
              `manim-dock sidecar exited with code ${code ?? "unknown"}`
          )
        );
        return;
      }
      try {
        resolve(JSON.parse(stdout) as T);
      } catch (err) {
        reject(
          new Error(
            `Failed to parse sidecar JSON: ${String(err)}\n${stdout}\n${stderr}`
          )
        );
      }
    });
  });
}

export class SidecarClient {
  constructor(private readonly extensionPath: string) {}

  private async python(): Promise<{ bin: string; cwd: string }> {
    const cwd = workspacePythonDir(this.extensionPath);
    const bin = await resolvePythonPath(this.extensionPath);
    return { bin, cwd };
  }

  async outline(filePath: string): Promise<FileOutline> {
    const { bin, cwd } = await this.python();
    return runPythonJson<FileOutline>(
      bin,
      ["-m", "manim_dock.cli", "outline", filePath],
      cwd
    );
  }

  async doctor(): Promise<{ probes: DoctorProbe[] }> {
    const { bin, cwd } = await this.python();
    return runPythonJson<{ probes: DoctorProbe[] }>(
      bin,
      ["-m", "manim_dock.cli", "doctor"],
      cwd
    );
  }
}
