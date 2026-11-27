const useColor = process.stdout.isTTY && !process.env.NO_COLOR;

const wrap = (code) => (text) => (useColor ? `\x1b[${code}m${text}\x1b[0m` : String(text));

export const ansi = {
  bold: wrap("1"),
  dim: wrap("2"),
  italic: wrap("3"),
  red: wrap("31"),
  green: wrap("32"),
  yellow: wrap("33"),
  blue: wrap("34"),
  magenta: wrap("35"),
  cyan: wrap("36"),
  gray: wrap("90"),
  white: wrap("97"),
  boldRed: wrap("1;31"),
  boldGreen: wrap("1;32"),
  boldYellow: wrap("1;33"),
  boldBlue: wrap("1;34"),
  boldCyan: wrap("1;36"),
  boldMagenta: wrap("1;35"),
  boldWhite: wrap("1;97"),
  bgDark: wrap("48;5;236"),
  bgPanel: wrap("48;5;235"),
  accentBlue: wrap("38;5;75"),
  c256: (n) => wrap(`38;5;${n}`),
};

export function renderLocAiLogo(termWidth = 78) {
  const rows = [
    ["██       ██████   ██████ ", "  █████  ██"],
    ["██      ██    ██ ██      ", " ██   ██ ██"],
    ["██      ██    ██ ██      ", " ███████ ██"],
    ["██      ██    ██ ██      ", " ██   ██ ██"],
    ["███████  ██████   ██████ ", " ██   ██ ██"],
  ];
  const rawLen = rows[0][0].length + rows[0][1].length;
  const leftPad = " ".repeat(Math.max(2, Math.floor((termWidth - rawLen) / 2)));

  return rows.map(([locPart, aiPart], idx) => {
    const locColor = idx < 3 ? ansi.c256(45) : ansi.c256(31);
    const aiColor = idx < 3 ? ansi.c256(214) : ansi.c256(172);
    return `${leftPad}${locColor(locPart)}${aiColor(aiPart)}`;
  });
}

export function stripAnsi(str = "") {
  return String(str).replace(/\x1b\[[0-9;]*m/g, "");
}

export function getTermWidth(maxWidth = 84) {
  const cols = process.stdout.columns || 76;
  return Math.max(44, Math.min(cols - 2, maxWidth));
}

export function padRightVisible(str, width) {
  const visible = stripAnsi(str).length;
  if (visible >= width) return str;
  return str + " ".repeat(width - visible);
}

export function truncateVisible(str, maxWidth) {
  if (stripAnsi(str).length <= maxWidth) return str;
  let visible = 0;
  let out = "";
  let i = 0;
  const s = String(str);
  while (i < s.length) {
    if (s[i] === "\x1b" && s[i + 1] === "[") {
      const end = s.indexOf("m", i);
      if (end !== -1) {
        out += s.slice(i, end + 1);
        i = end + 1;
        continue;
      }
    }
    if (visible >= maxWidth - 1) {
      out += "…\x1b[0m";
      break;
    }
    out += s[i];
    visible++;
    i++;
  }
  return out;
}

export function printRule(title = "") {
  const width = getTermWidth(80);
  if (!title) {
    console.log(ansi.gray("─".repeat(width)));
    return;
  }
  const pad = Math.max(2, Math.floor((width - stripAnsi(title).length - 2) / 2));
  console.log(`${ansi.gray("─".repeat(pad))} ${ansi.boldCyan(title)} ${ansi.gray("─".repeat(pad))}`);
}

export function renderBox(title, lines, footer = "", maxWidth = 78) {
  const width = getTermWidth(maxWidth);
  const inner = width - 4;
  const titleStr = title ? ` ${ansi.boldCyan(title)} ` : "";
  const titleLen = stripAnsi(titleStr).length;
  const topDashes = Math.max(2, width - 3 - titleLen);

  const out = [];
  out.push(`${ansi.gray("╭─")}${titleStr}${ansi.gray("─".repeat(topDashes) + "╮")}`);
  for (const line of lines) {
    const clipped = truncateVisible(line, inner);
    out.push(`${ansi.gray("│")} ${padRightVisible(clipped, inner)} ${ansi.gray("│")}`);
  }
  if (footer) {
    const footStr = ` ${ansi.gray(footer)} `;
    const footLen = stripAnsi(footStr).length;
    const botDashes = Math.max(2, width - 3 - footLen);
    out.push(`${ansi.gray("╰─")}${footStr}${ansi.gray("─".repeat(botDashes) + "╯")}`);
  } else {
    out.push(ansi.gray("╰" + "─".repeat(width - 2) + "╯"));
  }
  return out;
}
