import readline from "node:readline/promises";
import { stdin as input, stdout as output } from "node:process";
import { ansi, stripAnsi } from "./ansi.js";

const PASTE_START = "\x1b[200~";
const PASTE_END = "\x1b[201~";

/**
 * Normalize line endings and decide whether pasted text should be collapsed
 * into an OpenCode-style paste pill token.
 */
export function shouldCollapsePaste(text) {
  const normalized = String(text ?? "").replace(/\r\n/g, "\n").replace(/\r/g, "\n");
  return normalized.includes("\n") || normalized.length > 100;
}

export function formatPasteToken(id, text) {
  const normalized = String(text ?? "").replace(/\r\n/g, "\n").replace(/\r/g, "\n");
  const lines = normalized.split("\n").length;
  if (lines > 1) {
    return `[Pasted #${id} ~${lines} lines]`;
  }
  return `[Pasted #${id} ~${normalized.length} chars]`;
}

export function expandPastes(buffer, pastes) {
  let out = String(buffer ?? "");
  for (const [token, text] of pastes.entries()) {
    out = out.split(token).join(text);
  }
  return out;
}

function findTokenEndingAt(buffer, cursor, pastes) {
  for (const token of pastes.keys()) {
    if (cursor >= token.length && buffer.slice(cursor - token.length, cursor) === token) {
      return token;
    }
  }
  return null;
}

function findTokenStartingAt(buffer, cursor, pastes) {
  for (const token of pastes.keys()) {
    if (buffer.slice(cursor, cursor + token.length) === token) {
      return token;
    }
  }
  return null;
}

function renderBufferWithPills(buffer, pastes) {
  if (!pastes.size) return buffer;
  let rendered = buffer;
  for (const token of pastes.keys()) {
    if (rendered.includes(token)) {
      rendered = rendered.split(token).join(ansi.bgDark(ansi.boldCyan(token)));
    }
  }
  return rendered;
}

/**
 * OpenCode-style interactive prompt input with bracketed paste support.
 * - Multi-line or long pastes collapse into `[Pasted #N ~M lines]` pills.
 * - Backspace/Delete removes whole paste pills cleanly.
 * - Supports Ctrl+P (model selector), Up/Down history, Left/Right/Home/End, Ctrl+U/Ctrl+W.
 * - Falls back to standard readline when stdin is not a TTY.
 */
export async function readPromptInput({
  headerLine,
  promptPrefix = `${ansi.accentBlue("┃")} ${ansi.boldGreen("❯")} `,
  history = [],
  onCtrlP = null,
} = {}) {
  if (!input.isTTY) {
    const rl = readline.createInterface({ input, output });
    try {
      if (headerLine) output.write(`\n${headerLine}\n`);
      const line = await rl.question(promptPrefix);
      return { type: "submit", value: line };
    } catch {
      return { type: "eof" };
    } finally {
      rl.close();
    }
  }

  return await new Promise((resolve) => {
    let buffer = "";
    let cursor = 0;
    let historyIdx = history.length;
    let draftBeforeHistory = "";
    let pasteSeq = 0;
    const pastes = new Map();

    let inPaste = false;
    let pasteBuf = "";
    let chunkCarry = "";
    let prevVisualLines = 1;
    let settled = false;

    const prefixVisibleLen = stripAnsi(promptPrefix).length;

    const getVisualRows = (buf, cur) => {
      const cols = Math.max(20, output.columns || 80);
      const totalLen = prefixVisibleLen + buf.length;
      const totalRows = Math.max(1, Math.ceil(totalLen / cols));
      const curPos = prefixVisibleLen + cur;
      const curRow = Math.floor(curPos / cols);
      const curCol = curPos % cols;
      return { cols, totalRows, curRow, curCol };
    };

    const redraw = () => {
      // Move to start of current prompt block and clear downward
      if (prevVisualLines > 1) {
        output.write(`\x1b[${prevVisualLines - 1}F`);
      }
      output.write("\r\x1b[J");
      const styledBuf = renderBufferWithPills(buffer, pastes);
      output.write(`${promptPrefix}${styledBuf}`);

      const { totalRows, curRow, curCol } = getVisualRows(buffer, cursor);
      prevVisualLines = totalRows;

      // Move cursor to exact (curRow, curCol)
      const endRow = totalRows - 1;
      if (endRow > curRow) {
        output.write(`\x1b[${endRow - curRow}A`);
      }
      output.write("\r");
      if (curCol > 0) {
        output.write(`\x1b[${curCol}C`);
      }
    };

    const cleanup = () => {
      if (settled) return;
      settled = true;
      input.off("data", onData);
      output.write("\x1b[?2004l");
      if (input.isTTY) {
        try {
          input.setRawMode(false);
        } catch {
          // ignore if stream already closed
        }
        input.pause();
      }
    };

    const finish = (result) => {
      cleanup();
      resolve(result);
    };

    const insertText = (txt) => {
      buffer = buffer.slice(0, cursor) + txt + buffer.slice(cursor);
      cursor += txt.length;
    };

    const commitPaste = (rawText) => {
      const normalized = rawText.replace(/\r\n/g, "\n").replace(/\r/g, "\n");
      if (!normalized) return;
      if (shouldCollapsePaste(normalized)) {
        pasteSeq += 1;
        const token = formatPasteToken(pasteSeq, normalized);
        pastes.set(token, normalized);
        insertText(token);
      } else {
        insertText(normalized);
      }
    };

    const handleKeySequence = (seq) => {
      if (seq === "\x03") {
        // Ctrl+C
        if (buffer.length > 0) {
          buffer = "";
          cursor = 0;
          pastes.clear();
          redraw();
          return;
        }
        output.write("\n");
        finish({ type: "eof" });
        return;
      }

      if (seq === "\x04") {
        // Ctrl+D on empty line -> exit
        if (buffer.length === 0) {
          output.write("\n");
          finish({ type: "eof" });
          return;
        }
        return;
      }

      if (seq === "\x10") {
        // Ctrl+P -> model selector
        if (onCtrlP) {
          output.write("\n");
          finish({ type: "ctrl_p" });
        }
        return;
      }

      if (seq === "\r" || seq === "\n") {
        // Submit
        output.write("\n");
        const expanded = expandPastes(buffer, pastes);
        finish({ type: "submit", value: expanded });
        return;
      }

      if (seq === "\x1b\r" || seq === "\x1b\n" || seq === "\x1b[13;2u") {
        // Alt+Enter / Shift+Enter -> insert newline as a paste-safe line break
        insertText("\n");
        redraw();
        return;
      }

      if (seq === "\x7f" || seq === "\b") {
        // Backspace
        if (cursor === 0) return;
        const token = findTokenEndingAt(buffer, cursor, pastes);
        if (token) {
          buffer = buffer.slice(0, cursor - token.length) + buffer.slice(cursor);
          cursor -= token.length;
          if (!buffer.includes(token)) pastes.delete(token);
        } else {
          buffer = buffer.slice(0, cursor - 1) + buffer.slice(cursor);
          cursor -= 1;
        }
        redraw();
        return;
      }

      if (seq === "\x1b[3~") {
        // Delete
        if (cursor >= buffer.length) return;
        const token = findTokenStartingAt(buffer, cursor, pastes);
        if (token) {
          buffer = buffer.slice(0, cursor) + buffer.slice(cursor + token.length);
          if (!buffer.includes(token)) pastes.delete(token);
        } else {
          buffer = buffer.slice(0, cursor) + buffer.slice(cursor + 1);
        }
        redraw();
        return;
      }

      if (seq === "\x1b[D") {
        // Left
        if (cursor > 0) {
          const token = findTokenEndingAt(buffer, cursor, pastes);
          cursor -= token ? token.length : 1;
          redraw();
        }
        return;
      }

      if (seq === "\x1b[C") {
        // Right
        if (cursor < buffer.length) {
          const token = findTokenStartingAt(buffer, cursor, pastes);
          cursor += token ? token.length : 1;
          redraw();
        }
        return;
      }

      if (seq === "\x01" || seq === "\x1b[H" || seq === "\x1b[1~") {
        // Home / Ctrl+A
        cursor = 0;
        redraw();
        return;
      }

      if (seq === "\x05" || seq === "\x1b[F" || seq === "\x1b[4~") {
        // End / Ctrl+E
        cursor = buffer.length;
        redraw();
        return;
      }

      if (seq === "\x15") {
        // Ctrl+U: clear to start
        buffer = buffer.slice(cursor);
        cursor = 0;
        redraw();
        return;
      }

      if (seq === "\x17") {
        // Ctrl+W: delete previous word
        if (cursor === 0) return;
        const before = buffer.slice(0, cursor).replace(/\s+$/, "");
        const lastSpace = before.lastIndexOf(" ");
        const nextCursor = lastSpace === -1 ? 0 : lastSpace + 1;
        buffer = buffer.slice(0, nextCursor) + buffer.slice(cursor);
        cursor = nextCursor;
        redraw();
        return;
      }

      if (seq === "\x1b[A") {
        // Up arrow: history previous
        if (!history.length || historyIdx <= 0) return;
        if (historyIdx === history.length) draftBeforeHistory = buffer;
        historyIdx -= 1;
        buffer = history[historyIdx];
        cursor = buffer.length;
        pastes.clear();
        redraw();
        return;
      }

      if (seq === "\x1b[B") {
        // Down arrow: history next
        if (historyIdx >= history.length) return;
        historyIdx += 1;
        buffer = historyIdx === history.length ? draftBeforeHistory : history[historyIdx];
        cursor = buffer.length;
        pastes.clear();
        redraw();
        return;
      }

      // Ignore other ANSI escape sequences
      if (seq.startsWith("\x1b")) return;

      // Normal printable text
      insertText(seq);
      redraw();
    };

    const processInputString = (raw) => {
      let data = chunkCarry + raw;
      chunkCarry = "";

      while (data.length > 0 && !settled) {
        if (inPaste) {
          const endIdx = data.indexOf(PASTE_END);
          if (endIdx !== -1) {
            pasteBuf += data.slice(0, endIdx);
            commitPaste(pasteBuf);
            pasteBuf = "";
            inPaste = false;
            data = data.slice(endIdx + PASTE_END.length);
            redraw();
            continue;
          }
          // Check if data ends with a partial PASTE_END prefix
          let partialLen = 0;
          for (let k = Math.min(PASTE_END.length - 1, data.length); k >= 1; k--) {
            if (PASTE_END.startsWith(data.slice(-k))) {
              partialLen = k;
              break;
            }
          }
          if (partialLen > 0) {
            pasteBuf += data.slice(0, -partialLen);
            chunkCarry = data.slice(-partialLen);
          } else {
            pasteBuf += data;
          }
          break;
        }

        const startIdx = data.indexOf(PASTE_START);
        if (startIdx !== -1) {
          if (startIdx > 0) {
            processNonPasteChars(data.slice(0, startIdx));
          }
          inPaste = true;
          pasteBuf = "";
          data = data.slice(startIdx + PASTE_START.length);
          continue;
        }

        // Check for partial PASTE_START at end of chunk
        let partialStart = 0;
        for (let k = Math.min(PASTE_START.length - 1, data.length); k >= 1; k--) {
          if (PASTE_START.startsWith(data.slice(-k))) {
            partialStart = k;
            break;
          }
        }
        if (partialStart > 0) {
          processNonPasteChars(data.slice(0, -partialStart));
          chunkCarry = data.slice(-partialStart);
          break;
        }

        processNonPasteChars(data);
        break;
      }
    };

    const processNonPasteChars = (str) => {
      let i = 0;
      while (i < str.length && !settled) {
        if (str[i] === "\x1b") {
          // Match common CSI or Alt+Enter sequences
          const rest = str.slice(i);
          const csiMatch = rest.match(/^\x1b\[[0-9;]*[A-Za-z~]/);
          if (csiMatch) {
            handleKeySequence(csiMatch[0]);
            i += csiMatch[0].length;
            continue;
          }
          if (rest.length >= 2 && (rest[1] === "\r" || rest[1] === "\n")) {
            handleKeySequence(rest.slice(0, 2));
            i += 2;
            continue;
          }
          handleKeySequence("\x1b");
          i += 1;
          continue;
        }
        handleKeySequence(str[i]);
        i += 1;
      }
    };

    const onData = (buf) => {
      const str = typeof buf === "string" ? buf : buf.toString("utf8");
      processInputString(str);
    };

    if (headerLine) output.write(`\n${headerLine}\n`);
    output.write(promptPrefix);
    output.write("\x1b[?2004h");
    input.setEncoding("utf8");
    input.setRawMode(true);
    input.resume();
    input.on("data", onData);
  });
}
