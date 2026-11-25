import { stdin, stdout } from "node:process";
import { ansi, getTermWidth, padRightVisible, renderBox, stripAnsi } from "./ansi.js";

/**
 * OpenCode-style framed arrow-key selector using raw stdin (zero dependencies).
 * Returns the selected item's `value`, or `null` if cancelled (Esc / Ctrl+C / q).
 */
export async function selectWithArrows(title, items, currentValue = null) {
  if (!items || !items.length) return null;
  if (!stdin.isTTY) return null;

  let index = Math.max(
    0,
    items.findIndex((it) => it.value === currentValue)
  );
  let renderedLines = 0;

  const render = () => {
    if (renderedLines > 0) {
      stdout.write(`\x1b[${renderedLines}A\x1b[J`);
    }
    const boxWidth = getTermWidth(76);
    const inner = boxWidth - 4;
    const rows = items.map((it, i) => {
      const isSelected = i === index;
      const isCurrent = it.value === currentValue;
      const pointer = isSelected ? ansi.boldCyan("❯") : " ";
      const rawLabel = String(it.label || it.value);
      const match = rawLabel.match(/^(.*?)\s+(\[[^\]]+\])$/);
      const namePart = match ? match[1] : rawLabel;
      const providerPart = match ? match[2] : "";
      const activeBadge = isCurrent ? ansi.boldGreen(" ● aktif") : "";
      const rightText = `${providerPart ? ansi.dim(providerPart) : ""}${activeBadge}`;
      const rightLen = stripAnsi(rightText).length;
      const maxNameLen = Math.max(12, inner - rightLen - 4);
      const clippedName =
        namePart.length > maxNameLen ? namePart.slice(0, maxNameLen - 1) + "…" : namePart;
      const styledName = isSelected ? ansi.boldWhite(clippedName) : ansi.dim(clippedName);
      const leftText = `${pointer} ${styledName}`;
      const gap = Math.max(1, inner - stripAnsi(leftText).length - rightLen);
      return padRightVisible(`${leftText}${" ".repeat(gap)}${rightText}`, inner);
    });

    const boxLines = renderBox(title, rows, "↑/↓ gez · Enter seç · Esc/q iptal", 76);
    stdout.write(boxLines.join("\n") + "\n");
    renderedLines = boxLines.length;
  };

  return new Promise((resolve) => {
    const wasRaw = Boolean(stdin.isRaw);
    stdin.setRawMode(true);
    stdin.resume();
    stdout.write("\x1b[?25l");
    render();

    const cleanup = () => {
      stdin.removeListener("data", onData);
      try {
        stdin.setRawMode(wasRaw);
      } catch {
        // ignore
      }
      stdout.write("\x1b[?25h");
    };

    const onData = (buf) => {
      const key = buf.toString("utf8");

      if (key === "\x03" || key === "\x1b" || key === "q") {
        cleanup();
        resolve(null);
        return;
      }

      if (key === "\r" || key === "\n") {
        cleanup();
        resolve(items[index].value);
        return;
      }

      if (key === "\x1b[A" || key === "\x1bOA" || key === "k") {
        index = (index - 1 + items.length) % items.length;
        render();
        return;
      }

      if (key === "\x1b[B" || key === "\x1bOB" || key === "j") {
        index = (index + 1) % items.length;
        render();
        return;
      }
    };

    stdin.on("data", onData);
  });
}
