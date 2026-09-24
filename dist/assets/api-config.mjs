export function normalizeApiOrigin(value, pageProtocol = 'https:') {
  const url = new URL(value.trim());
  const local = ['localhost', '127.0.0.1', '[::1]'].includes(url.hostname);
  if (url.protocol !== 'https:' && !(local && url.protocol === 'http:' && pageProtocol === 'http:')) {
    throw new Error('Use an HTTPS API address. HTTP localhost is supported only from a local HTTP page.');
  }
  if (url.username || url.password || url.search || url.hash || !['', '/'].includes(url.pathname)) {
    throw new Error('Enter only the server origin, for example https://fales-api.example.com (without /api).');
  }
  return url.origin;
}
