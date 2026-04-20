import { NextRequest } from 'next/server'

export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ repoId: string }> },
) {
  const { repoId } = await params
  const body = await req.json()

  const upstream = await fetch(
    `${process.env.BACKEND_STREAMING_URL}/repos/${repoId}/query`,
    {
      method: 'POST',
      headers: {
        'content-type': 'application/json',
        'x-api-key': process.env.BACKEND_API_KEY ?? '',
      },
      body: JSON.stringify(body),
    },
  )

  return new Response(upstream.body, {
    status: upstream.status,
    headers: {
      'content-type': 'application/x-ndjson',
      'x-accel-buffering': 'no',
      'cache-control': 'no-cache',
      'transfer-encoding': 'chunked',
    },
  })
}
