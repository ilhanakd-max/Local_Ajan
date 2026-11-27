import fs from "node:fs";
import path from "node:path";
import {
  getProfileForModel,
  resolveDynamicNumCtx,
  scanWorkspaceSize,
} from "../llm/modelProfiles.js";
import { chatStreamOllama } from "../llm/ollamaClient.js";
import { chatStreamOpenAICompat, resolveProvider } from "../llm/openaiCompatClient.js";
import { registry } from "../tools/index.js";
import { confirmAction } from "../safety/confirm.js";
import { RepetitionLoopGuard, detectTextRepetition } from "../safety/guards.js";
import { getSafePath } from "../safety/sandbox.js";
import { ansi } from "../ui/ansi.js";
import { ChatHistory } from "./history.js";
import { prepareContext, truncateToolOutput } from "./context.js";
import { extractAllToolCalls } from "./parser.js";
import { getSystemPrompt } from "./prompt.js";
import { filterThinkingStream, stripThinking } from "./thinking.js";
import { WorkLog } from "./workLog.js";

const TOOL_MARKER_RE =
  /(<\s*\/?\s*t\s*o\s*o\s*l|<tool_call|<tool_|<\|tool_call_start|<\s*f\s*u\s*n\s*c\s*t\s*i\s*o\s*n|<delegate_task|<write_file|<arg_key|```(?:json)?\s*\{|\{\s*"name"\s*:|\[(?:write_file|read_file|edit_file|list_dir|glob|grep|git_status|git_diff|run_shell|delegate_task|report_finding|semantic_code_search)\()/i;

const PARTIAL_TAG_RE =
  /(<\s*\/?\s*t[a-zA-Z0-9_\s]*|<tool_?[a-zA-Z0-9_]*|<\|tool_?[a-zA-Z0-9_]*|<\s*\/?\s*f[a-zA-Z0-9_\s]*|\[(?:delegate|write|read|edit|list|glob|grep|git|run)[a-zA-Z0-9_]*)$/i;

const MALFORMED_TAG_RE = /<tool_call|<\|tool_call_start\|>|<function[=\s]/i;

function formatArgsPreview(args = {}) {
  const preview = {};
  for (const [k, v] of Object.entries(args)) {
    if (typeof v === "string" && v.length > 140) {
      preview[k] = `${v.slice(0, 140)}... (${v.length} krk)`;
    } else if (Array.isArray(v) && v.length > 5) {
      preview[k] = [...v.slice(0, 5), `... (${v.length} öğe)`];
    } else {
      preview[k] = v;
    }
  }
  return JSON.stringify(preview);
}

function attachReferencedFiles(userInput, workdir, quiet = false) {
  const raw = String(userInput || "").trim();
  if (!raw) return userInput;

  const candidates = new Set();
  for (const m of raw.matchAll(/['"]([^'"]+)['"]/g)) {
    candidates.add(m[1].trim());
  }
  for (const m of raw.matchAll(/(?:^|\s)((?:\/|\.\/|\.\.\/)?[\w.\-/\\]+\.[a-zA-Z0-9]{1,10})(?=$|\s)/g)) {
    candidates.add(m[1].trim());
  }

  const attached = [];
  const seenFiles = new Set();
  for (const cand of candidates) {
    if (!cand || cand.includes("://")) continue;
    try {
      const safe = getSafePath(cand, workdir);
      if (seenFiles.has(safe) || !fs.existsSync(safe)) continue;
      const stat = fs.statSync(safe);
      if (!stat.isFile()) continue;
      const buf = fs.readFileSync(safe);
      if (buf.includes(0)) continue; // skip binary files
      seenFiles.add(safe);
      const rel = path.relative(workdir, safe) || path.basename(safe);
      const text = buf.toString("utf8");
      const maxChars = 12000;
      const body = text.length > maxChars
        ? `${text.slice(0, maxChars)}\n... [kısaltıldı: toplam ${text.length} karakter]`
        : text;
      attached.push({ rel, body, chars: text.length });
    } catch {
      // ignore invalid or out-of-workdir paths
    }
  }

  if (!attached.length) return userInput;

  if (!quiet) {
    for (const f of attached) {
      console.log(ansi.dim(`  📎 ${f.rel} (${f.chars} krk) otomatik eklendi`));
    }
  }

  const strippedOnlyPaths = raw
    .replace(/['"][^'"]+['"]/g, "")
    .replace(/(?:^|\s)(?:\/|\.\/|\.\.\/)?[\w.\-/\\]+\.[a-zA-Z0-9]{1,10}(?=$|\s)/g, "")
    .trim();

  const blocks = attached
    .map((f) => `<attached_file path="${f.rel}">\n${f.body}\n</attached_file>`)
    .join("\n\n");

  if (!strippedOnlyPaths) {
    return `Kullanıcı aşağıdaki yerel dosyayı paylaştı. İçeriğini incele, ne istendiğini özetle veya uygulanması gereken adımları belirt:\n\n${blocks}`;
  }
  return `${userInput}\n\n${blocks}`;
}

export class AgentLoop {
  constructor({
    modelName,
    host = "http://localhost:11434",
    workdir = null,
    autoConfirm = false,
    maxSteps = 20,
    config = {},
    workerModel = null,
    ponytailMode = false,
    streamFn = null,
    quiet = false,
  }) {
    this.modelName = modelName;
    this.host = host;
    this.workdir = workdir || process.cwd();
    this.autoConfirm = autoConfirm;
    this.maxSteps = maxSteps;
    this.config = config;
    this.workerModel = workerModel;
    this.ponytailMode = ponytailMode;
    this.streamFn = streamFn;
    this.quiet = quiet;

    registry.setWorkdir(this.workdir);
    this.profile = getProfileForModel(modelName);
    this.workspaceStats = scanWorkspaceSize(this.workdir);
    this.activeNumCtx = resolveDynamicNumCtx({
      modelName: this.modelName,
      baseNumCtx: this.profile.num_ctx,
      workspaceStats: this.workspaceStats,
    });
    this.history = new ChatHistory(this._buildPrompt());
    this.workLog = new WorkLog(this.workdir);
  }

  _buildPrompt() {
    return getSystemPrompt({
      promptLevel: this.profile.prompt_level,
      orchestratorMode: Boolean(this.workerModel),
      workerModel: this.workerModel,
      ponytailMode: this.ponytailMode,
    });
  }

  refreshPrompt() {
    this.profile = getProfileForModel(this.modelName);
    this.activeNumCtx = resolveDynamicNumCtx({
      modelName: this.modelName,
      baseNumCtx: this.profile.num_ctx,
      workspaceStats: this.workspaceStats,
    });
    this.history.updateSystemPrompt(this._buildPrompt());
  }

  setModel(newModel) {
    this.modelName = newModel;
    this.refreshPrompt();
  }

  setPonytailMode(enabled) {
    this.ponytailMode = Boolean(enabled);
    this.refreshPrompt();
  }

  async *_streamModel(messages) {
    if (this.streamFn) {
      yield* this.streamFn({
        model: this.modelName,
        messages,
        profile: this.profile,
        numCtx: this.activeNumCtx,
      });
      return;
    }

    if (resolveProvider(this.modelName, this.config)) {
      yield* chatStreamOpenAICompat({
        model: this.modelName,
        messages,
        config: this.config,
        temperature: this.profile.temperature,
      });
      return;
    }

    const thinkOpt = this.profile.supports_think_control ? !this.profile.disable_thinking : null;
    yield* chatStreamOllama({
      model: this.modelName,
      messages,
      host: this.host,
      numCtx: this.activeNumCtx,
      temperature: this.profile.temperature,
      repeatPenalty: this.profile.repeat_penalty,
      numPredict: this.profile.num_predict || 0,
      topK: this.profile.top_k || 0,
      topP: this.profile.top_p || 0,
      think: thinkOpt,
    });
  }

  async _delegateTask({ task_description, context_files = [] }) {
    if (!this.workerModel) {
      return "Error: Worker model is not configured.";
    }
    const worker = new AgentLoop({
      modelName: this.workerModel,
      host: this.host,
      workdir: this.workdir,
      autoConfirm: this.autoConfirm,
      maxSteps: 12,
      config: this.config,
      ponytailMode: this.ponytailMode,
      streamFn: this.streamFn,
      quiet: true,
    });
    const ctxNote = context_files.length ? `\nRelevant files: ${context_files.join(", ")}` : "";
    return worker.runTurn(`${task_description}${ctxNote}`);
  }

  async runTurn(userInput) {
    const enrichedInput = attachReferencedFiles(userInput, this.workdir, this.quiet);
    this.history.addUser(enrichedInput);
    this.workLog.add("GÖREV", String(userInput || "").slice(0, 160));
    if (this.history.getMessages().length > 40 && !this._historyWarned && !this.quiet) {
      console.log(ansi.dim("💡 İpucu: Oturum geçmişi uzadı. Belleği tazelemek için '/save <ad>' ardından '/clear' yapabilirsiniz."));
      this._historyWarned = true;
    }

    const loopGuard = new RepetitionLoopGuard();
    const extraNames = this.workerModel ? new Set(["delegate_task"]) : null;
    const retryLimit = this.profile.parse_retry_limit ?? 2;
    let parseFailCount = 0;
    let finalResponse = "";

    for (let step = 0; step < this.maxSteps; step++) {
      const workLogSummary = this.workLog.formatForPrompt(12);
      const msgs = this.history.getMessages();
      const messagesChars = msgs.reduce((acc, m) => acc + (m.content?.length || 0), 0) + workLogSummary.length;
      const nextCtx = resolveDynamicNumCtx({
        modelName: this.modelName,
        baseNumCtx: this.profile.num_ctx,
        workspaceStats: this.workspaceStats,
        messagesChars,
      });
      if (nextCtx > this.activeNumCtx) {
        if (!this.quiet) {
          console.log(ansi.dim(`  ⚡ Bağlam penceresi otomatik artırıldı: ${this.activeNumCtx} → ${nextCtx} token`));
        }
        this.activeNumCtx = nextCtx;
      }
      const prepared = prepareContext(
        msgs,
        this.activeNumCtx,
        0.35,
        workLogSummary,
        step >= 3
      );
      let rawOutput = "";
      let printedLen = 0;
      let tokenCount = 0;
      let inToolMode = false;
      let spinnerActive = false;
      let repetitionAborted = false;
      const isTTY = Boolean(process.stdout.isTTY);
      const spinnerChars = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"];

      if (!this.quiet) {
        process.stdout.write(`\n${ansi.boldCyan("◆ LocAi")} ${ansi.gray("·")} ${ansi.dim(this.modelName)}\n`);
      }

      for await (const chunk of filterThinkingStream(this._streamModel(prepared))) {
        rawOutput += chunk;
        tokenCount++;

        if (tokenCount % 25 === 0 && detectTextRepetition(rawOutput)) {
          repetitionAborted = true;
          break;
        }

        if (this.quiet) continue;

        const marker = TOOL_MARKER_RE.exec(rawOutput);
        if (marker) {
          const cutIndex = marker.index;
          if (printedLen < cutIndex) {
            const pending = rawOutput.slice(printedLen, cutIndex);
            if (pending) {
              if (spinnerActive) {
                if (isTTY) process.stdout.write("\r\x1b[K");
                else process.stdout.write("\n");
                spinnerActive = false;
              }
              process.stdout.write(pending);
              printedLen = cutIndex;
            }
          }
          if (!inToolMode) {
            inToolMode = true;
            if (printedLen > 0 && !rawOutput.slice(0, printedLen).endsWith("\n")) {
              process.stdout.write("\n");
            }
          }
          const sp = spinnerChars[tokenCount % spinnerChars.length];
          if (isTTY) {
            process.stdout.write(`\r\x1b[K  ${sp} ${ansi.boldCyan(`⚡ Kod / Araç çağrısı üretiliyor (${tokenCount} parça)...`)}`);
            spinnerActive = true;
          } else if (!spinnerActive || tokenCount % 30 === 0) {
            console.log(`  ${sp} ${ansi.boldCyan(`⚡ Kod / Araç çağrısı üretiliyor (${tokenCount} parça)...`)}`);
            spinnerActive = true;
          }
        } else {
          const tail = rawOutput.slice(printedLen);
          const partial = PARTIAL_TAG_RE.exec(tail);
          if (partial && tail.length - partial.index < 35) {
            const safeLen = printedLen + partial.index;
            if (safeLen > printedLen) {
              if (spinnerActive) {
                if (isTTY) process.stdout.write("\r\x1b[K");
                else process.stdout.write("\n");
                spinnerActive = false;
              }
              process.stdout.write(rawOutput.slice(printedLen, safeLen));
              printedLen = safeLen;
            }
          } else if (tail) {
            if (spinnerActive) {
              if (isTTY) process.stdout.write("\r\x1b[K");
              else process.stdout.write("\n");
              spinnerActive = false;
            }
            process.stdout.write(tail);
            printedLen = rawOutput.length;
          }
        }
      }

      if (!this.quiet) {
        if (spinnerActive) {
          if (isTTY) process.stdout.write("\r\x1b[K\n");
          else process.stdout.write("\n");
        } else if (printedLen > 0 && !rawOutput.slice(0, printedLen).endsWith("\n")) {
          process.stdout.write("\n");
        } else if (printedLen === 0) {
          process.stdout.write("\n");
        }
      }

      const cleaned = stripThinking(rawOutput);
      this.history.addAssistant(cleaned);

      if (repetitionAborted) {
        const msg = "[Döngü Koruması: Model aynı metni tekrarlamaya başladığı için yanıt durduruldu.]";
        if (!this.quiet) console.log(ansi.yellow(msg));
        return cleaned || msg;
      }

      const calls = extractAllToolCalls(cleaned, extraNames);

      // Flush unprinted normal text if no tool calls were detected
      if (!this.quiet && !calls.length && cleaned.trim() && printedLen < rawOutput.length) {
        const rest = rawOutput.slice(printedLen);
        if (rest.trim()) console.log(rest);
      }

      // Small-model recovery 1: Empty / think-only output
      if (!calls.length && !cleaned.trim()) {
        parseFailCount++;
        if (parseFailCount <= retryLimit) {
          if (!this.quiet) {
            console.log(ansi.dim(`Yanıt boş geldi, düzeltme isteği gönderiliyor (${parseFailCount}/${retryLimit})...`));
          }
          this.history.addUser(
            "Yanıtın boş geldi. Ya bir <tool_call> bloğu üret ya da kullanıcıya kısa, normal bir cevap yaz. Başka bir şey yazma."
          );
          continue;
        }
        if (!this.quiet) console.log(ansi.red("Model tekrar tekrar boş yanıt üretti, döngü durduruldu."));
        break;
      }

      // Small-model recovery 2: Empty LFM tool tags
      const withoutEmptyLfm = cleaned.replace(/<\|tool_call_start\|>\s*<\|tool_call_end\|>/g, "").trim();
      if (!calls.length && !withoutEmptyLfm) {
        parseFailCount++;
        if (parseFailCount <= retryLimit) {
          if (!this.quiet) {
            console.log(ansi.dim(`Model boş tool etiketi üretti, düzeltme gönderiliyor (${parseFailCount}/${retryLimit})...`));
          }
          this.history.addUser(
            "You produced empty tool call tags with no content. Either produce a valid <tool_call> block with a tool name and arguments, or write a short answer to the user."
          );
          continue;
        }
        if (!this.quiet) console.log(ansi.red("Model tekrar tekrar boş tool etiketi üretti, döngü durduruldu."));
        break;
      }

      // Small-model recovery 3: Malformed / unparsed tool call tags
      if (!calls.length && MALFORMED_TAG_RE.test(cleaned)) {
        parseFailCount++;
        if (parseFailCount <= retryLimit) {
          if (!this.quiet) {
            console.log(ansi.dim(`Bozuk araç çağrısı algılandı, düzeltme gönderiliyor (${parseFailCount}/${retryLimit})...`));
          }
          this.history.addUser(
            'Araç çağrın geçersiz biçimdeydi ve çalıştırılamadı. Lütfen geçerli bir JSON formatında <tool_call>{"name": "tool_name", "arguments": {...}}</tool_call> bloğu üret ve devam et.'
          );
          continue;
        }
        if (!this.quiet) console.log(ansi.red("Model tekrar tekrar bozuk araç çağrısı üretti, döngü durduruldu."));
        break;
      }

      if (!calls.length) {
        finalResponse = cleaned;
        if (finalResponse.trim()) {
          this.workLog.add("YANIT", finalResponse.slice(0, 160));
        }
        break;
      }

      parseFailCount = 0;

      for (const call of calls) {
        if (!this.quiet) {
          console.log(`  ${ansi.gray("├─")} ${ansi.boldMagenta("⚙ " + call.name)} ${ansi.dim(formatArgsPreview(call.args))}`);
        }

        const guardRes = loopGuard.recordAndCheck(call.name, call.args);
        if (guardRes.blocked) {
          const warn = `Loop guard blocked '${call.name}': ${guardRes.reason}. Change approach or answer directly.`;
          this.history.addToolResult(call.name, warn);
          if (!this.quiet) console.log(ansi.yellow(`⚠ ${warn}`));
          if (guardRes.shouldAbort) {
            return `Stopped after repeated tool-call loop: ${guardRes.reason}`;
          }
          continue;
        }

        if (call.name === "delegate_task") {
          const workerOut = await this._delegateTask(call.args || {});
          const truncated = truncateToolOutput(workerOut, this.profile.max_tool_output);
          this.history.addToolResult("delegate_task", truncated);
          continue;
        }

        const tool = registry.get(call.name);
        if (!tool) {
          this.history.addToolResult(call.name, `Error: Unknown tool '${call.name}'.`);
          continue;
        }

        const needsConfirm =
          tool.requiresConfirm &&
          (this.config.require_confirm_for || ["write_file", "edit_file", "run_shell"]).includes(tool.name);

        if (needsConfirm) {
          const ok = await confirmAction(`'${tool.name}' çalıştırılsın mı?`, this.autoConfirm);
          if (!ok) {
            this.history.addToolResult(tool.name, "User declined tool execution.");
            if (!this.quiet) console.log(ansi.dim("  (Kullanıcı tarafından reddedildi)"));
            continue;
          }
        }

        let result;
        try {
          result = await tool.run(call.args || {});
        } catch (err) {
          result = `Error executing '${tool.name}': ${err.message}`;
        }

        const truncated = truncateToolOutput(
          String(result ?? ""),
          this.profile.max_tool_output,
          tool.name === "run_shell" ? Math.floor(this.profile.max_tool_output / 4) : 0
        );
        const previewLine = truncated.split("\n")[0].slice(0, 120);
        this.workLog.add(tool.name, `${formatArgsPreview(call.args || {})} -> ${previewLine}`);
        this.history.addToolResult(
          tool.name,
          `${truncated}\n(Kalan başka işlem yoksa görevi bitir; kodu tekrar yazma, 1 kısa cümleyle ne yapıldığını söyle ve dur.)`
        );
        if (!this.quiet) {
          const preview = truncated.split("\n")[0].slice(0, 120);
          const isErr = /^(Error|Hata)/i.test(preview);
          const badge = isErr ? ansi.red("✗") : ansi.green("✓");
          console.log(`  ${ansi.gray("└─")} ${badge} ${ansi.dim(preview)}`);
        }
      }
    }

    return finalResponse;
  }
}
