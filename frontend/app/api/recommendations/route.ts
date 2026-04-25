import { NextRequest, NextResponse } from "next/server"

export async function GET(request: NextRequest) {
  const apiUrl = process.env.LIVE_URL?.trim().replace(/\/+$/, '')
  const apiKey = process.env.API_KEY?.trim()

  if (!apiUrl || !apiKey) {
    return NextResponse.json(
      { 
        error: "Backend API not configured. Please set LIVE_URL and API_KEY environment variables.",
        items: [] 
      },
      { status: 200 }
    )
  }

  // Get limit from query params (default 50, max 200)
  const searchParams = request.nextUrl.searchParams
  const limit = Math.min(Math.max(parseInt(searchParams.get("limit") || "50"), 1), 200)

try {
    const url = `${apiUrl}/recommendations?limit=${limit}`
    
    const response = await fetch(url, {
      headers: {
        Authorization: `Bearer ${apiKey}`,
        "Content-Type": "application/json",
      },
      cache: "no-store",
    })

    if (!response.ok) {
      return NextResponse.json(
        { 
          error: `Backend returned ${response.status}`,
          items: []
        },
        { status: 200 }
      )
    }

    const data = await response.json()
    return NextResponse.json(data)
  } catch (error) {
    return NextResponse.json(
      { 
        error: error instanceof Error ? error.message : "Failed to fetch recommendations",
        items: []
      },
      { status: 200 }
    )
  }
}
