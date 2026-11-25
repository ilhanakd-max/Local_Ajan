const CHARS_PER_TOKEN = 3.5;

const TRUNCATION_NOTICE =
  "[Not: Bağlam penceresi sınırlı olduğu için önceki konuşmadan bazı eski mesajlar kırpıldı. Sistem talimatı ve en güncel mesajlar korunuyor.]";

export function truncateToolOutput(output, maxLength = 2000) {
  if (!output || output.length <= maxLength) return output;
  return (
    output.slice(0, maxLength) +
    `\n\n... (Çıktı ${maxLength} karaktere kırpıldı. Devamını görmek için aracı tekrar, uygun parametrelerle çağırın.)`
  );
}

export function prepareContext(messages, maxContext = 4096, reserveForOutputRatio = 0.35) {
  if (!messages || !messages.length) return messages;

  const systemMessages = messages.filter((m) => m.role === "system");
  const rest = messages.filter((m) => m.role !== "system");

  const budgetTokens = Math.floor(maxContext * (1 - reserveForOutputRatio));
  const budgetChars = Math.max(500, Math.floor(budgetTokens * CHARS_PER_TOKEN));

  let used = systemMessages.reduce((acc, m) => acc + (m.content?.length || 0), 0);
  if (used >= budgetChars) {
    return [...systemMessages, ...rest];
  }

  const keptReversed = [];
  let dropped = false;
  for (let i = rest.length - 1; i >= 0; i--) {
    const msg = rest[i];
    const len = msg.content?.length || 0;
    if (used + len > budgetChars && keptReversed.length > 0) {
      dropped = true;
      continue;
    }
    keptReversed.push(msg);
    used += len;
  }

  let kept = keptReversed.reverse();
  if (dropped) {
    kept = [{ role: "user", content: TRUNCATION_NOTICE }, ...kept];
  }
  return [...systemMessages, ...kept];
}
