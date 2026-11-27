import readline from "node:readline/promises";
import { stdin as input, stdout as output } from "node:process";
import { ansi } from "../ui/ansi.js";

export async function confirmAction(message, autoConfirm = false) {
  if (autoConfirm) return true;
  if (!input.isTTY) return false;
  input.resume();
  const rl = readline.createInterface({ input, output });
  try {
    const ans = await rl.question(`${ansi.boldYellow("?")} ${message} [y/N]: `);
    return /^y(es)?|e(vet)?$/i.test(ans.trim());
  } finally {
    rl.close();
  }
}
