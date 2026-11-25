const OPEN = "<think>";
const CLOSE = "</think>";

export function stripThinking(text) {
  if (!text || (!text.includes(OPEN) && !text.includes(CLOSE))) {
    return text;
  }
  const out = [];
  let i = 0;
  const n = text.length;
  while (i < n) {
    const start = text.indexOf(OPEN, i);
    if (start === -1) {
      out.push(text.slice(i));
      break;
    }
    out.push(text.slice(i, start));
    const end = text.indexOf(CLOSE, start + OPEN.length);
    if (end === -1) {
      i = n;
      break;
    }
    i = end + CLOSE.length;
  }
  return out.join("").trim();
}

export async function* filterThinkingStream(chunks) {
  let buf = "";
  let inThink = false;
  const marginOpen = OPEN.length - 1;
  const marginClose = CLOSE.length - 1;

  for await (const chunk of chunks) {
    if (!chunk) continue;
    buf += chunk;

    while (true) {
      if (!inThink) {
        const idx = buf.indexOf(OPEN);
        if (idx === -1) {
          const safeLen = Math.max(0, buf.length - marginOpen);
          if (safeLen > 0) {
            yield buf.slice(0, safeLen);
            buf = buf.slice(safeLen);
          }
          break;
        } else {
          if (idx > 0) yield buf.slice(0, idx);
          buf = buf.slice(idx + OPEN.length);
          inThink = true;
        }
      } else {
        const idx = buf.indexOf(CLOSE);
        if (idx === -1) {
          const safeLen = Math.max(0, buf.length - marginClose);
          buf = buf.slice(safeLen);
          break;
        } else {
          buf = buf.slice(idx + CLOSE.length);
          inThink = false;
        }
      }
    }
  }

  if (!inThink && buf) {
    yield buf;
  }
}
