import { stdin as input, stdout as output } from "node:process";
import { parseArgs } from "node:util";
import { loadConfig, saveState } from "./config.js";
import { listOllamaModels } from "./llm/ollamaClient.js";
import { AgentLoop } from "./agent/loop.js";
import { saveSession, loadSession, listSessions } from "./agent/session.js";
import os from "node:os";
import {
  ansi,
  getTermWidth,
  padRightVisible,
  renderLocAiLogo,
  stripAnsi,
  truncateVisible,
} from "./ui/ansi.js";
import { selectWithArrows } from "./ui/selector.js";
import { readPromptInput } from "./ui/promptInput.js";

const VERSION = "0.4.0-js";

function printHelp() {
  console.log(`
${ansi.boldCyan("LocAi (Node.js)")} v${VERSION} — Gizlilik odaklı yerel AI kodlama ajanı

Kullanım:
  locai [seçenekler]

Seçenekler:
  -m, --model <ad>       Kullanılacak model (örn. qwen3:1.7b, openrouter/free, groq/...)
  -w, --worker <ad>      Orkestratör modu için alt-işçi (worker) modeli
      --host <url>       Ollama adresi (varsayılan: http://localhost:11434)
      --workdir <dizin>  Çalışma dizini (varsayılan: mevcut dizin)
  -p, --prompt <metin>   Tek seferlik görev çalıştır ve çık
  -y, --auto-confirm     Dosya yazma/düzenleme ve shell komutlarını otomatik onayla (varsayılan: açık; kapatmak için --no-auto-confirm)
      --ponytail         Minimalist kodlama modu (sıfır aşırı mühendislik)
      --session <ad>     Kayıtlı oturumu yükle
  -v, --version          Sürüm bilgisini göster
  -h, --help             Yardım mesajını göster

REPL Komutları:
  /help                  Komutları listele
  /model [ad]            Model seçiciyi aç (veya Ctrl+P) / model değiştir
  /clear                 Sohbet geçmişini temizle
  /history               Mesaj sayısını ve aktif modeli göster
  /save <ad>             Oturumu kaydet
  /load <ad>             Oturumu yükle
  /sessions              Kayıtlı oturumları listele
  /ponytail              Ponytail (minimalist) modunu aç/kapat
  /exit                  Çıkış yap
`);
}

function buildModelChoices(config, ollamaModels, currentModel) {
  const seen = new Set();
  const items = [];
  const pushItem = (value, tag = "") => {
    if (!value || seen.has(value)) return;
    seen.add(value);
    items.push({
      value,
      label: tag ? `${value} ${ansi.dim(`[${tag}]`)}` : value,
    });
  };

  for (const m of ollamaModels) pushItem(m, "Ollama");
  if (config.openrouter_api_key) pushItem("openrouter/free", "OpenRouter");
  if (config.groq_api_key) pushItem("groq/llama-3.3-70b-versatile", "Groq");
  if (config.ninerouter_api_key) pushItem("ninerouter/default", "NineRouter");
  if (config.nvidia_api_key) pushItem("nvidia/meta/llama-3.3-70b-instruct", "NVIDIA");
  pushItem(currentModel, "Aktif");

  return items;
}

async function openInteractiveModelSelector(agent, config, pauseReadline) {
  const ollamaModels = await listOllamaModels(config.ollama_host);
  const choices = buildModelChoices(config, ollamaModels, agent.modelName);
  if (!choices.length) {
    console.log(ansi.dim("  (Ollama'ya ulaşılamadı veya yüklü model yok)"));
    return;
  }

  if (input.isTTY) {
    if (pauseReadline) pauseReadline();
    const chosen = await selectWithArrows("Model Seçin:", choices, agent.modelName);
    if (chosen) {
      agent.setModel(chosen);
      saveState({ model: chosen });
      console.log(ansi.green(`✓ Model değiştirildi: ${chosen}`));
    } else {
      console.log(ansi.dim("Model seçimi iptal edildi."));
    }
    return;
  }

  console.log(ansi.boldCyan("Kullanılabilir Modeller:"));
  for (const c of choices) {
    const mark = c.value === agent.modelName ? ansi.boldGreen(" ◄ aktif") : "";
    console.log(`  - ${c.label}${mark}`);
  }
  console.log(ansi.dim("Değiştirmek için: /model <model_adı>"));
}

async function handleSlashCommand(line, agent, config, pauseReadline) {
  const parts = line.trim().split(/\s+/);
  const cmd = parts[0].toLowerCase();
  const arg = parts.slice(1).join(" ").trim();

  if (cmd === "/exit" || cmd === "/quit") return "EXIT";
  if (cmd === "/help") {
    printHelp();
    return "HANDLED";
  }
  if (cmd === "/clear") {
    agent.history.clear();
    console.log(ansi.green("✓ Sohbet geçmişi temizlendi."));
    return "HANDLED";
  }
  if (cmd === "/history") {
    console.log(
      `${ansi.cyan("Model:")} ${agent.modelName} | ${ansi.cyan("Mesajlar:")} ${agent.history.getMessages().length} | ${ansi.cyan("Ponytail:")} ${agent.ponytailMode ? "Açık" : "Kapalı"}`
    );
    return "HANDLED";
  }
  if (cmd === "/ponytail") {
    agent.setPonytailMode(!agent.ponytailMode);
    console.log(ansi.green(`✓ Ponytail modu: ${agent.ponytailMode ? "Açık" : "Kapalı"}`));
    return "HANDLED";
  }
  if (cmd === "/save") {
    if (!arg) {
      console.log(ansi.yellow("Kullanım: /save <oturum_adı>"));
      return "HANDLED";
    }
    const file = saveSession(arg, {
      model: agent.modelName,
      messages: agent.history.getMessages(),
      workdir: agent.workdir,
    });
    console.log(ansi.green(`✓ Oturum kaydedildi: ${file}`));
    return "HANDLED";
  }
  if (cmd === "/load") {
    if (!arg) {
      console.log(ansi.yellow("Kullanım: /load <oturum_adı>"));
      return "HANDLED";
    }
    const data = loadSession(arg);
    if (!data) {
      console.log(ansi.red(`✗ Oturum bulunamadı: ${arg}`));
      return "HANDLED";
    }
    agent.history.messages = data.messages || [];
    if (data.model) agent.setModel(data.model);
    console.log(ansi.green(`✓ Oturum yüklendi: ${arg} (${agent.history.getMessages().length} mesaj)`));
    return "HANDLED";
  }
  if (cmd === "/sessions") {
    const items = listSessions();
    if (!items.length) {
      console.log(ansi.dim("Kayıtlı oturum yok."));
    } else {
      for (const s of items) {
        console.log(`- ${ansi.boldCyan(s.name)} (${s.model}, ${s.messageCount} mesaj)`);
      }
    }
    return "HANDLED";
  }
  if (cmd === "/model") {
    if (arg) {
      agent.setModel(arg);
      saveState({ model: arg });
      console.log(ansi.green(`✓ Model değiştirildi: ${arg}`));
      return "HANDLED";
    }
    await openInteractiveModelSelector(agent, config, pauseReadline);
    return "HANDLED";
  }

  console.log(ansi.yellow(`Bilinmeyen komut: ${cmd}. Yardım için /help yazın.`));
  return "HANDLED";
}

function formatShortDir(dir) {
  const home = os.homedir();
  return dir.startsWith(home) ? "~" + dir.slice(home.length) : dir;
}

function printPanelLine(content, width) {
  const bar = ansi.accentBlue("┃");
  const inner = width - 2;
  const clipped = truncateVisible(content, inner);
  const padded = padRightVisible(clipped, inner);
  console.log(`${bar}${ansi.bgPanel(padded)}`);
}

function printWelcomeBanner(agent) {
  const width = getTermWidth(78);
  const modeTag = agent.ponytailMode ? ansi.magenta(" (ponytail)") : ansi.gray(" (standart)");
  const shortDir = formatShortDir(agent.workdir);

  console.log("");
  for (const row of renderLocAiLogo(width)) {
    console.log(row);
  }
  console.log("");

  printPanelLine("", width);
  printPanelLine(`  ${ansi.gray('Herhangi bir şey sor... "kodu incele" veya "/help"')}`, width);
  printPanelLine("", width);
  printPanelLine(
    `  ${ansi.accentBlue("Build")} ${ansi.gray("·")} ${ansi.boldWhite(agent.modelName)}${modeTag}`,
    width
  );

  const leftHint = `  ${ansi.dim(shortDir)}`;
  const rightHint = `${ansi.boldWhite("ctrl+p")} ${ansi.gray("model seç")}   ${ansi.boldWhite("/help")} ${ansi.gray("komutlar")}`;
  const gap1 = Math.max(2, width - stripAnsi(leftHint).length - stripAnsi(rightHint).length);
  console.log(`${leftHint}${" ".repeat(gap1)}${rightHint}`);
  console.log("");

  const footLeft = `  ${ansi.green("●")} ${ansi.boldWhite("Hazır")} ${ansi.gray("/help")}`;
  const footRight = ansi.gray(`v${VERSION}`);
  const gap2 = Math.max(2, width - stripAnsi(footLeft).length - stripAnsi(footRight).length);
  console.log(`${footLeft}${" ".repeat(gap2)}${footRight}`);
}

export async function main(argv = process.argv.slice(2)) {
  const { values } = parseArgs({
    args: argv,
    options: {
      model: { type: "string", short: "m" },
      worker: { type: "string", short: "w" },
      host: { type: "string" },
      workdir: { type: "string" },
      prompt: { type: "string", short: "p" },
      "auto-confirm": { type: "boolean", short: "y", default: true },
      ponytail: { type: "boolean", default: false },
      session: { type: "string" },
      version: { type: "boolean", short: "v", default: false },
      help: { type: "boolean", short: "h", default: false },
    },
    allowPositionals: true,
    allowNegative: true,
  });

  if (values.version) {
    console.log(`LocAi (Node.js) v${VERSION}`);
    return;
  }
  if (values.help) {
    printHelp();
    return;
  }

  const config = loadConfig();
  const modelName = values.model || config.default_model;
  const host = values.host || config.ollama_host;
  const workdir = values.workdir || process.cwd();

  const agent = new AgentLoop({
    modelName,
    host,
    workdir,
    autoConfirm: values["auto-confirm"],
    maxSteps: config.max_steps,
    config,
    workerModel: values.worker || null,
    ponytailMode: values.ponytail,
  });

  if (values.session) {
    const data = loadSession(values.session);
    if (data && Array.isArray(data.messages)) {
      agent.history.messages = data.messages;
      if (data.model) agent.setModel(data.model);
      console.log(ansi.green(`✓ Oturum yüklendi: ${values.session}`));
    }
  }

  if (values.prompt) {
    await agent.runTurn(values.prompt);
    return;
  }

  printWelcomeBanner(agent);

  const promptHistory = [];
  const pauseReadline = () => {};

  while (true) {
    const modeTag = agent.ponytailMode ? ` ${ansi.gray("·")} ${ansi.magenta("ponytail")}` : "";
    const headerLine = `${ansi.accentBlue("┃")} ${ansi.accentBlue("Build")} ${ansi.gray("·")} ${ansi.dim(agent.modelName)}${modeTag}`;
    const promptPrefix = `${ansi.accentBlue("┃")} ${ansi.boldGreen("❯")} `;

    const resInput = await readPromptInput({
      headerLine,
      promptPrefix,
      history: promptHistory,
      onCtrlP: () => {},
    });

    if (resInput.type === "ctrl_p") {
      await openInteractiveModelSelector(agent, config, pauseReadline);
      continue;
    }
    if (resInput.type === "eof") {
      break;
    }

    const trimmed = resInput.value.trim();
    if (!trimmed) continue;
    promptHistory.push(trimmed);

    if (trimmed.startsWith("/")) {
      const res = await handleSlashCommand(trimmed, agent, config, pauseReadline);
      if (res === "EXIT") break;
      continue;
    }
    try {
      await agent.runTurn(trimmed);
    } catch (err) {
      console.log(ansi.red(`Hata: ${err.message}`));
    }
  }
}
