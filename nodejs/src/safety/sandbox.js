import fs from "node:fs";
import path from "node:path";

export function getSafePath(targetPath, workdir = null) {
  const baseDir = path.resolve(workdir || process.cwd());
  let realBase = baseDir;
  try {
    realBase = fs.realpathSync(baseDir);
  } catch {
    // use resolved path if base does not exist yet
  }

  const candidate = path.isAbsolute(targetPath)
    ? path.resolve(targetPath)
    : path.resolve(baseDir, targetPath);

  let realTarget = candidate;
  if (fs.existsSync(candidate)) {
    try {
      realTarget = fs.realpathSync(candidate);
    } catch {
      realTarget = candidate;
    }
  } else {
    const parent = path.dirname(candidate);
    if (fs.existsSync(parent)) {
      try {
        realTarget = path.join(fs.realpathSync(parent), path.basename(candidate));
      } catch {
        realTarget = candidate;
      }
    }
  }

  const rel = path.relative(realBase, realTarget);
  if (rel.startsWith("..") || path.isAbsolute(rel)) {
    throw new Error(
      `Güvenlik İhlali: '${targetPath}' çalışma dizini (${realBase}) dışına çıkıyor.`
    );
  }
  return realTarget;
}

const DANGEROUS_PATTERNS = [
  /\brm\s+-[rRfF]*[rR][rRfF]*\s+\/(\s|$|\*)/,
  /\bmkfs\b/,
  /\bdd\s+if=.*of=\/dev\//,
  /:\(\)\s*\{\s*:\|:\s*&\s*\};:/,
  /\bchmod\s+-R\s+777\s+\//,
  /\bshutdown\b|\breboot\b|\bpoweroff\b/,
];

export function isDangerousShellCommand(cmd) {
  return DANGEROUS_PATTERNS.some((re) => re.test(cmd));
}
