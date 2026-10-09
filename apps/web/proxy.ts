import { NextRequest, NextResponse } from 'next/server';
export function proxy(request: NextRequest) {
  const password = process.env.DASHBOARD_PASSWORD;
  if (password) {
    const header = request.headers.get('authorization');
    const expected = `Basic ${Buffer.from(`admin:${password}`).toString('base64')}`;
    if (header !== expected) return new NextResponse('Dashboard authentication required', { status: 401, headers: { 'WWW-Authenticate': 'Basic realm="AgentScope"' } });
  }
  return NextResponse.next();
}
export const config = { matcher: ['/((?!_next/static|_next/image|favicon.ico).*)'] };
