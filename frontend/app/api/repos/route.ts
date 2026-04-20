import { NextRequest } from 'next/server'

export async function POST(req: NextRequest) {
  const body = await req.json()
  const res = await fetch(`${process.env.BACKEND_API_URL}/repos`, {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      'x-api-key': process.env.BACKEND_API_KEY ?? '',
    },
    body: JSON.stringify(body),
  })
  const data = await res.json()
  return Response.json(data, { status: res.status })
}
