import { spawn } from "child_process";
import * as fs from "fs";
import * as path from "path";

/** ManimCE media folder for a quality letter. */
export function qualityDir(quality: string): string {
  const q = (quality || "l").trim().toLowerCase();
  const letter =
    q === "m" || q === "medium"
      ? "m"
      : q === "h" || q === "high"
        ? "h"
        : q === "k" || q === "4k"
          ? "k"
          : "l";
  return (
    {
      l: "480p15",
      m: "720p30",
      h: "1080p60",
      k: "2160p60",
    } as Record<string, string>
  )[letter];
}

/** Relative concat.txt lines for ffmpeg demuxer. */
export function buildConcatLines(
  moduleStem: string,
  quality: string,
  sceneNames: string[]
): string {
  const dir = qualityDir(quality);
  return sceneNames
    .map(
      (name) =>
        `file 'media/videos/${moduleStem}/${dir}/${name}.mp4'`
    )
    .join("\n") + (sceneNames.length ? "\n" : "");
}

export function writeConcatFile(
  scriptDir: string,
  moduleStem: string,
  quality: string,
  sceneNames: string[]
): string {
  const concatPath = path.join(scriptDir, "concat.txt");
  fs.writeFileSync(
    concatPath,
    buildConcatLines(moduleStem, quality, sceneNames),
    "utf8"
  );
  return concatPath;
}

export function runFfmpegConcat(
  scriptDir: string,
  concatFileName: string = "concat.txt",
  outputName: string = "final.mp4"
): Promise<{ ok: boolean; outputPath: string; error?: string; log?: string }> {
  const outputPath = path.join(scriptDir, outputName);
  return new Promise((resolve) => {
    const child = spawn(
      "ffmpeg",
      ["-y", "-f", "concat", "-safe", "0", "-i", concatFileName, "-c", "copy", outputName],
      { cwd: scriptDir }
    );
    let log = "";
    child.stderr?.on("data", (chunk: Buffer) => {
      log += chunk.toString();
    });
    child.on("error", (err) => {
      const msg = String(err);
      resolve({
        ok: false,
        outputPath,
        error: msg.includes("ENOENT")
          ? "ffmpeg not found on PATH — install ffmpeg to stitch scenes"
          : msg,
        log,
      });
    });
    child.on("close", (code) => {
      if (code === 0 && fs.existsSync(outputPath)) {
        resolve({ ok: true, outputPath, log });
        return;
      }
      resolve({
        ok: false,
        outputPath,
        error: `ffmpeg exited with code ${code ?? "?"}`,
        log: log.slice(-4000),
      });
    });
  });
}
