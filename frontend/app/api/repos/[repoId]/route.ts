import { NextRequest } from 'next/server'

export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ repoId: string }> },
) {
  const { repoId } = await params
  const res = await fetch(`${process.env.BACKEND_API_URL}/repos/${repoId}`, {
    headers: { 'x-api-key': process.env.BACKEND_API_KEY ?? '' },
    cache: 'no-store',
  })
  const data = await res.json()
  return Response.json(data, { status: res.status })
}
