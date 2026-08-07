import * as vscode from "vscode";
import { confirmAndApplyPatches, PendingPatch } from "./patchConfirm";
import { SidecarClient } from "./sidecar";

const ALIGN_MODES = [
  "left",
  "right",
  "center_x",
  "top",
  "bottom",
  "center_y",
  "distribute_x",
  "distribute_y",
] as const;

/**
 * Multi-select Stage align/distribute via relative shift patches.
 */
export async function applyAlignPatches(
  context: vscode.ExtensionContext,
  sidecar: SidecarClient,
  output: vscode.OutputChannel,
  filePath: string,
  sceneName: string,
  names: string[],
  mode: string,
  channel: string
): Promise<boolean> {
  if (!(ALIGN_MODES as readonly string[]).includes(mode)) {
    return false;
  }
  if (names.length < 2) {
    void vscode.window.showWarningMessage(
      "Manim Dock: Shift/Ctrl-click two or more Stage proxies, then Align."
    );
    return false;
  }

  let layout;
  try {
    const doc = await vscode.workspace.openTextDocument(filePath);
    layout = await sidecar.layout(filePath, sceneName, doc.getText());
  } catch (err) {
    void vscode.window.showErrorMessage(
      `Manim Dock align failed: ${String(err)}`
    );
    return false;
  }

  const items = names
    .map((name) => layout.items.find((i) => i.name === name))
    .filter((i): i is NonNullable<typeof i> => !!i)
    .map((i) => ({ name: i.name, x: i.x, y: i.y }));

  if (items.length < 2) {
    void vscode.window.showWarningMessage(
      "Manim Dock: could not resolve layout positions for selection."
    );
    return false;
  }

  let deltas;
  try {
    deltas = await sidecar.alignDeltas(mode, items);
  } catch (err) {
    void vscode.window.showErrorMessage(
      `Manim Dock align failed: ${String(err)}`
    );
    return false;
  }

  const pendings: PendingPatch[] = [];
  let source = (await vscode.workspace.openTextDocument(filePath)).getText();
  for (const delta of deltas) {
    if (Math.abs(delta.dx) < 1e-9 && Math.abs(delta.dy) < 1e-9) {
      continue;
    }
    const item = layout.items.find((i) => i.name === delta.name);
    let proposal;
    try {
      proposal = await sidecar.proposeShift(
        filePath,
        delta.name,
        delta.dx,
        delta.dy,
        source,
        item?.range.start_line
      );
    } catch (err) {
      void vscode.window.showErrorMessage(
        `Manim Dock align patch failed for ${delta.name}: ${String(err)}`
      );
      return false;
    }
    if (!proposal.ok) {
      void vscode.window.showWarningMessage(
        `Manim Dock: ${proposal.error ?? `align patch failed for ${delta.name}`}`
      );
      return false;
    }
    pendings.push({
      path: proposal.path,
      original: proposal.original,
      proposed: proposal.proposed,
      summary: proposal.summary,
      diff: proposal.diff,
    });
    source = proposal.proposed;
  }

  if (!pendings.length) {
    void vscode.window.showInformationMessage(
      "Manim Dock: selection already aligned."
    );
    return false;
  }

  return confirmAndApplyPatches(
    context,
    pendings,
    output,
    channel,
    `align ${mode}`
  );
}
