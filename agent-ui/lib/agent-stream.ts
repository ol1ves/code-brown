import type { AgentEvent } from "./types"

export function parseSseBuffer(buffer: string): { events: AgentEvent[]; rest: string } {
  const packets = buffer.split("\n\n")
  const rest = packets.pop() ?? ""
  const events: AgentEvent[] = []

  for (const packet of packets) {
    const line = packet
      .split("\n")
      .find((v) => v.startsWith("data: "))
    if (!line) continue
    const payload = line.slice("data: ".length).trim()
    try {
      events.push(JSON.parse(payload) as AgentEvent)
    } catch {
      // ignore invalid packets and continue stream
    }
  }
  return { events, rest }
}

export async function streamAgentRun(
  intentText: string,
  onEvent: (event: AgentEvent) => void,
): Promise<void> {
  const response = await fetch("/api/agent/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ intent_text: intentText }),
  })
  if (!response.ok || !response.body) {
    throw new Error(`Stream failed (${response.status})`)
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder("utf-8")
  let buffer = ""

  while (true) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const parsed = parseSseBuffer(buffer)
    buffer = parsed.rest
    for (const event of parsed.events) onEvent(event)
  }
}
