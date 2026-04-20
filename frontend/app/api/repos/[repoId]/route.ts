import { NextRequest } from 'next/server'

export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ repoId: string }> },
) {
  const { repoId } = await params
  const res = await fetch(`${process.env.AWS_API_URL}/repos/${repoId}`, {
    headers: { 'x-api-key': process.env.AWS_API_KEY ?? '' },
  })
  const data = await res.json()
  return Response.json(data, { status: res.status })
}
