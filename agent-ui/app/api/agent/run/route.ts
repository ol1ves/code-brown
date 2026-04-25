import { NextRequest } from "next/server"

export const runtime = "nodejs"
export const dynamic = "force-dynamic"

export async function POST(request: NextRequest) {
  const apiUrl = process.env.LIVE_URL?.trim().replace(/\/+$/, "")
  const apiKey = process.env.API_KEY?.trim()
  if (!apiUrl || !apiKey) {
    return new Response(JSON.stringify({ error: "Missing LIVE_URL or API_KEY" }), {
      status: 500,
      headers: { "Content-Type": "application/json" },
    })
  }

  const body = await request.text()
  const upstream = await fetch(`${apiUrl}/agent/run`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${apiKey}`,
      "Content-Type": "application/json",
    },
    body,
  })

  if (!upstream.ok || !upstream.body) {
    const text = await upstream.text().catch(() => "")
    return new Response(
      JSON.stringify({ error: `Backend returned ${upstream.status}`, detail: text }),
      { status: upstream.status, headers: { "Content-Type": "application/json" } },
    )
  }

  return new Response(upstream.body, {
    status: 200,
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      Connection: "keep-alive",
    },
  })
}
