/* Pistes Quad – espace de données par utilisateur (Cloudflare Pages Function + KV).
   L'utilisateur est identifié par Cloudflare Access : on vérifie la signature du jeton
   (Cf-Access-Jwt-Assertion) avec les clés publiques de l'équipe Zero Trust.
   Variables à définir dans le projet Pages :
     TEAM_DOMAIN = somatcha.cloudflareaccess.com   (domaine de l'équipe Zero Trust)
     POLICY_AUD  = Application Audience (AUD) Tag de l'application Access « Pistes Quad »
   Liaison KV : DATA → espace de noms « pistes-quad-donnees » */
const MAX_BYTES = 5_000_000;
const json = (o, status = 200) => new Response(JSON.stringify(o), { status, headers: { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' } });
const b64u = s => { s = s.replace(/-/g, '+').replace(/_/g, '/'); while (s.length % 4) s += '='; return Uint8Array.from(atob(s), c => c.charCodeAt(0)); };
const b64uText = s => new TextDecoder().decode(b64u(s));
function cookie(req, name) { const c = req.headers.get('Cookie') || ''; const m = c.match(new RegExp('(?:^|;\\s*)' + name + '=([^;]+)')); return m ? m[1] : null; }

let certCache = { t: 0, keys: [] };
async function certs(team) {
  if (Date.now() - certCache.t < 3600e3 && certCache.keys.length) return certCache.keys;
  const r = await fetch(`https://${team}/cdn-cgi/access/certs`);
  const j = await r.json();
  certCache = { t: Date.now(), keys: j.keys || [] };
  return certCache.keys;
}
async function identify(request, env) {
  const token = request.headers.get('Cf-Access-Jwt-Assertion') || cookie(request, 'CF_Authorization');
  if (!token || !env.TEAM_DOMAIN || !env.POLICY_AUD) return null;
  const parts = token.split('.');
  if (parts.length !== 3) return null;
  let header, payload;
  try { header = JSON.parse(b64uText(parts[0])); payload = JSON.parse(b64uText(parts[1])); } catch (e) { return null; }
  const aud = Array.isArray(payload.aud) ? payload.aud : [payload.aud];
  if (!aud.includes(env.POLICY_AUD)) return null;
  if (!payload.exp || payload.exp * 1000 < Date.now()) return null;
  if (payload.iss && payload.iss !== `https://${env.TEAM_DOMAIN}`) return null;
  const jwk = (await certs(env.TEAM_DOMAIN)).find(k => k.kid === header.kid);
  if (!jwk) return null;
  const key = await crypto.subtle.importKey('jwk', { kty: jwk.kty, n: jwk.n, e: jwk.e, alg: 'RS256', ext: true }, { name: 'RSASSA-PKCS1-v1_5', hash: 'SHA-256' }, false, ['verify']);
  const ok = await crypto.subtle.verify('RSASSA-PKCS1-v1_5', key, b64u(parts[2]), new TextEncoder().encode(parts[0] + '.' + parts[1]));
  return ok && payload.email ? String(payload.email).toLowerCase() : null;
}

export async function onRequest({ request, env }) {
  let email;
  try { email = await identify(request, env); } catch (e) { email = null; }
  if (!email) return json({ error: 'non connecté', configured: !!(env.TEAM_DOMAIN && env.POLICY_AUD) }, 401);
  if (!env.DATA) return json({ error: 'stockage non configuré', email }, 503);
  const key = 'user:' + email;
  if (request.method === 'GET') {
    const v = await env.DATA.get(key);
    return json({ email, data: v ? JSON.parse(v) : null });
  }
  if (request.method === 'PUT') {
    const t = await request.text();
    if (t.length > MAX_BYTES) return json({ error: 'données trop volumineuses' }, 413);
    try { JSON.parse(t); } catch (e) { return json({ error: 'format invalide' }, 400); }
    await env.DATA.put(key, t);
    return json({ ok: true, email, size: t.length });
  }
  return json({ error: 'méthode non autorisée' }, 405);
}
