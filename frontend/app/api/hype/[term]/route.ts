import { NextRequest, NextResponse } from "next/server"

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ term: string }> }
) {
  const apiUrl = process.env.LIVE_URL?.trim().replace(/\/+$/, '')
  const apiKey = process.env.API_KEY?.trim()
  const { term } = await params

  if (!apiUrl || !apiKey) {
    return NextResponse.json(
      { error: "Backend API not configured. Please set LIVE_URL and API_KEY environment variables." },
      { status: 500 }
    )
  }

  try {
    const response = await fetch(`${apiUrl}/hype/${encodeURIComponent(term)}`, {
      headers: {
        Authorization: `Bearer ${apiKey}`,
        "Content-Type": "application/json",
      },
      cache: "no-store",
    })

    if (!response.ok) {
      const errorText = await response.text().catch(() => "")
      console.error("[v0] Hype error:", response.status, errorText)
      return NextResponse.json(
        { error: `Backend returned ${response.status}: ${errorText}` },
        { status: response.status }
      )
    }

    const data = await response.json()
    return NextResponse.json(data)
  } catch (error) {
    console.error("[v0] Error fetching hype score:", error)
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Failed to fetch hype score" },
      { status: 500 }
    )
  }
}
