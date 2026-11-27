const CHARS_PER_TOKEN = 3.5;

const TRUNCATION_NOTICE =
  "[Not: Bağlam penceresi sınırlı olduğu için önceki konuşmadan bazı eski mesajlar kırpıldı. Sistem talimatı ve en güncel mesajlar korunuyor.]";

export function truncateToolOutput(output, maxLength = 2000, keepTail = 0) {
  if (!output || output.length <= maxLength) return output;
  if (keepTail > 0 && keepTail < maxLength) {
    // Kabuk çıktılarında hata/stack-trace sondadır: baş + son kısmı koru.
    const head = output.slice(0, maxLength - keepTail);
    const tail = output.slice(-keepTail);
    const omitted = output.length - head.length - tail.length;
    return `${head}\n\n... (${omitted} karakter atlandı; baş ve son kısım gösteriliyor.) ...\n\n${tail}`;
  }
  return (
    output.slice(0, maxLength) +
    `\n\n... (Çıktı ${maxLength} karaktere kırpıldı. Devamını görmek için aracı tekrar, uygun parametrelerle çağırın.)`
  );
}

export function prepareContext(
  messages,
  maxContext = 4096,
  reserveForOutputRatio = 0.35,
  workLogSummary = "",
  forceWorkLog = false
) {
  if (!messages || !messages.length) return messages;

  const systemMessages = messages.filter((m) => m.role === "system");
  const rest = messages.filter((m) => m.role !== "system");

  const budgetTokens = Math.floor(maxContext * (1 - reserveForOutputRatio));
  const budgetChars = Math.max(500, Math.floor(budgetTokens * CHARS_PER_TOKEN));

  const logBlock = workLogSummary ? String(workLogSummary).trim() : "";
  const reservedLogChars = logBlock ? Math.min(logBlock.length + 120, Math.floor(budgetChars * 0.25)) : 0;

  let used = systemMessages.reduce((acc, m) => acc + (m.content?.length || 0), 0);
  if (used >= budgetChars) {
    return [...systemMessages, ...rest];
  }

  const effectiveBudget = Math.max(500, budgetChars - reservedLogChars);
  const keptReversed = [];
  let dropped = false;
  for (let i = rest.length - 1; i >= 0; i--) {
    const msg = rest[i];
    const len = msg.content?.length || 0;
    if (used + len > effectiveBudget && keptReversed.length > 0) {
      dropped = true;
      continue;
    }
    keptReversed.push(msg);
    used += len;
  }

  let kept = keptReversed.reverse();
  if (dropped || (forceWorkLog && logBlock)) {
    const noticeParts = [];
    if (dropped) noticeParts.push(TRUNCATION_NOTICE);
    if (logBlock) noticeParts.push(logBlock);
    kept = [{ role: "user", content: noticeParts.join("\n\n") }, ...kept];
  }
  return [...systemMessages, ...kept];
}
