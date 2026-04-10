import { NextRequest, NextResponse } from 'next/server';

const EXPLAINABILITY_URL = process.env.EXPLAINABILITY_URL
  || (process.env.DOCKER_CONTAINER ? 'http://explainability:8009' : 'http://localhost:8009');

/**
 * POST /api/explain
 *
 * Proxies to the real explainability service at port 8009.
 * Accepts the same payload as POST /explain/transaction on the backend.
 */
export async function POST(req: NextRequest) {
  try {
    const body = await req.json();

    const res = await fetch(`${EXPLAINABILITY_URL}/explain/transaction`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(5000),
    });

    if (!res.ok) {
      const text = await res.text().catch(() => '');
      console.error(`Explainability service error ${res.status}: ${text}`);
      return NextResponse.json(
        { error: 'Explainability service unavailable', status: res.status },
        { status: 502 },
      );
    }

    const data = await res.json();
    return NextResponse.json(data);
  } catch (err) {
    console.error('Explainability proxy error:', err);
    return NextResponse.json(
      { error: 'Failed to reach explainability service' },
      { status: 502 },
    );
  }
}

/**
 * GET /api/explain  –  health check passthrough
 */
export async function GET() {
  try {
    const res = await fetch(`${EXPLAINABILITY_URL}/health`, {
      signal: AbortSignal.timeout(3000),
    });
    const data = await res.json();
    return NextResponse.json(data);
  } catch {
    return NextResponse.json({ status: 'unreachable' }, { status: 502 });
  }
}
