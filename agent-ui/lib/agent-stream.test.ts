import { describe, expect, it } from "vitest"
import { parseSseBuffer } from "./agent-stream"

describe("parseSseBuffer", () => {
  it("parses multi-event packet", () => {
    const input = 'data: {"type":"plan_thinking","delta":"a"}\n\ndata: {"type":"done"}\n\n'
    const out = parseSseBuffer(input)
    expect(out.events).toHaveLength(2)
    expect(out.events[0].type).toBe("plan_thinking")
    expect(out.events[1].type).toBe("done")
    expect(out.rest).toBe("")
  })

  it("keeps incomplete chunk in rest", () => {
    const input = 'data: {"type":"plan_thinking","delta":"a"}\n\ndata: {"type":"do'
    const out = parseSseBuffer(input)
    expect(out.events).toHaveLength(1)
    expect(out.rest).toContain('data: {"type":"do')
  })
})
