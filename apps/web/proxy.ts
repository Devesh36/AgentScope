import { NextRequest, NextResponse } from 'next/server';
import { readFileSync } from 'node:fs';
import { timingSafeEqual } from 'node:crypto';
import captures from './lib/terminal-screenshots.json';
const publicDocsAssets = new Set([
  '/docs-assets/cli-start.png',
  '/docs-assets/cli-demo.png',
  '/docs-assets/terminal-tour/agentscope-terminal-tour.pdf',
  ...captures.map((capture) => `/docs-assets/terminal-tour/${capture.name}.png`),
]);
export function proxy(request: NextRequest) {
  // Public product documentation and its screenshots do not expose workspace data.
  const pathname = request.nextUrl.pathname;
  if (pathname === '/' || pathname === '/docs' || pathname === '/docs/' || publicDocsAssets.has(pathname)) return NextResponse.next();
  let password = process.env.DASHBOARD_PASSWORD;
  if (process.env.DASHBOARD_PASSWORD_FILE) {
    try {
      password = readFileSync(/* turbopackIgnore: true */ process.env.DASHBOARD_PASSWORD_FILE, 'utf8').trim();
      if (!password) throw new Error('Empty secret');
    } catch {
      return new NextResponse('Dashboard authentication configuration unavailable', { status: 503 });
    }
  }
  if (process.env.AGENTSCOPE_CONTAINER === '1' && !password) {
    return new NextResponse('Dashboard authentication configuration required', { status: 503 });
  }
  if (password) {
    const header = request.headers.get('authorization');
    const expected = `Basic ${Buffer.from(`admin:${password}`).toString('base64')}`;
    const received = Buffer.from(header || '');
    const wanted = Buffer.from(expected);
    if (received.length !== wanted.length || !timingSafeEqual(received, wanted)) return new NextResponse('Dashboard authentication required', { status: 401, headers: { 'WWW-Authenticate': 'Basic realm="AgentScope"' } });
  }
  return NextResponse.next();
}
export const config = { matcher: ['/((?!_next/static|_next/image|favicon.ico).*)'] };
