import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

function resolveApiBase(): string {
  const raw =
    process.env.QT_INTERNAL_API_URL ||
    process.env.NEXT_PUBLIC_API_URL ||
    "http://127.0.0.1:8000";
  return raw.replace(/\/+$/, "");
}

async function proxyRequest(
  req: NextRequest,
  context: { params: Promise<{ path: string[] }> }
): Promise<NextResponse> {
  const { path } = await context.params;
  const upstreamUrl = `${resolveApiBase()}/api/${path.join("/")}${req.nextUrl.search}`;

  const forwardHeaders = new Headers();
  req.headers.forEach((value, key) => {
    const lower = key.toLowerCase();
    if (lower !== "host" && lower !== "connection" && lower !== "content-length") {
      forwardHeaders.set(key, value);
    }
  });

  const hasBody = req.method !== "GET" && req.method !== "HEAD";
  const bodyBuffer = hasBody ? await req.arrayBuffer() : undefined;

  try {
    const upstreamRes = await fetch(upstreamUrl, {
      method: req.method,
      headers: forwardHeaders,
      body: hasBody ? bodyBuffer : undefined,
      redirect: "manual",
    });

    const responseHeaders = new Headers();
    upstreamRes.headers.forEach((value, key) => {
      const lower = key.toLowerCase();
      if (
        lower !== "transfer-encoding" &&
        lower !== "content-encoding" &&
        lower !== "content-length"
      ) {
        responseHeaders.set(key, value);
      }
    });

    const payload = await upstreamRes.arrayBuffer();
    return new NextResponse(payload, {
      status: upstreamRes.status,
      headers: responseHeaders,
    });
  } catch (err) {
    const detail = err instanceof Error ? err.message : "Backend API unreachable";
    return NextResponse.json(
      { detail: `QueryTrellis API proxy error (${upstreamUrl}): ${detail}` },
      { status: 502 }
    );
  }
}

export async function GET(
  req: NextRequest,
  context: { params: Promise<{ path: string[] }> }
) {
  return proxyRequest(req, context);
}

export async function POST(
  req: NextRequest,
  context: { params: Promise<{ path: string[] }> }
) {
  return proxyRequest(req, context);
}

export async function PUT(
  req: NextRequest,
  context: { params: Promise<{ path: string[] }> }
) {
  return proxyRequest(req, context);
}

export async function PATCH(
  req: NextRequest,
  context: { params: Promise<{ path: string[] }> }
) {
  return proxyRequest(req, context);
}

export async function DELETE(
  req: NextRequest,
  context: { params: Promise<{ path: string[] }> }
) {
  return proxyRequest(req, context);
}
