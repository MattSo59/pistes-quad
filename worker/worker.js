/* Pistes Quad – Worker Cloudflare
   - sert l'appli (actifs statiques)
   - /api/* : comptes (e-mail + mot de passe), validation par l'administrateur, données par utilisateur
   Stockage KV (liaison DATA) :
     acct:<email>  → { email, name, salt, hash, status: pending|approved|refused, created, approvedAt }
     sess:<jeton>  → email (expire seul au bout de 60 jours)
     data:<email>  → données synchronisées de l'appli (historique, favoris, notes, sorties…)
     fail:<email>  → compteur d'échecs de connexion (15 min)
   Variable : ADMIN_EMAIL (compte validé d'office, peut valider les autres). */

const ORIGINS = ['https://quad.team-somatcha.fr', 'https://mattso59.github.io'];
const SESSION_TTL = 60 * 24 * 3600;
const PBKDF2_ITER = 100000;
const MAX_DATA = 5_000_000;

const enc = new TextEncoder();
const hex = b => [...new Uint8Array(b)].map(x => x.toString(16).padStart(2, '0')).join('');
const unhex = h => Uint8Array.from(h.match(/../g).map(x => parseInt(x, 16)));
const randHex = n => hex(crypto.getRandomValues(new Uint8Array(n)));
const normEmail = e => String(e || '').trim().toLowerCase();
const validEmail = e => /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(e) && e.length <= 120;

function cors(req) {
  const o = req.headers.get('Origin');
  const h = { 'Vary': 'Origin' };
  if (o && (ORIGINS.includes(o) || /^http:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/.test(o))) {
    h['Access-Control-Allow-Origin'] = o;
    h['Access-Control-Allow-Headers'] = 'Authorization, Content-Type';
    h['Access-Control-Allow-Methods'] = 'GET, POST, PUT, OPTIONS';
    h['Access-Control-Max-Age'] = '86400';
  }
  return h;
}
const json = (req, o, status = 200) => new Response(JSON.stringify(o), {
  status, headers: { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store', ...cors(req) }
});

async function hashPw(pw, saltHex) {
  const key = await crypto.subtle.importKey('raw', enc.encode(pw), 'PBKDF2', false, ['deriveBits']);
  const bits = await crypto.subtle.deriveBits({ name: 'PBKDF2', hash: 'SHA-256', salt: unhex(saltHex), iterations: PBKDF2_ITER }, key, 256);
  return hex(bits);
}
function sameStr(a, b) { if (a.length !== b.length) return false; let r = 0; for (let i = 0; i < a.length; i++) r |= a.charCodeAt(i) ^ b.charCodeAt(i); return r === 0; }
const getJ = async (env, k) => { const v = await env.DATA.get(k); return v ? JSON.parse(v) : null; };
const pub = (a, env) => ({ email: a.email, name: a.name || '', status: a.status, created: a.created, admin: a.email === normEmail(env.ADMIN_EMAIL) });

async function session(req, env) {
  const m = (req.headers.get('Authorization') || '').match(/^Bearer ([0-9a-f]{64})$/);
  if (!m) return null;
  const email = await env.DATA.get('sess:' + m[1]);
  if (!email) return null;
  const a = await getJ(env, 'acct:' + email);
  if (!a || a.status !== 'approved') return null;
  return { token: m[1], acct: a };
}
async function body(req) { try { return await req.json(); } catch (e) { return {}; } }

async function api(req, env, path) {
  if (req.method === 'OPTIONS') return new Response(null, { status: 204, headers: cors(req) });
  if (!env.DATA) return json(req, { error: 'Stockage non configuré.' }, 503);
  const admin = normEmail(env.ADMIN_EMAIL);

  if (path === '/api/register' && req.method === 'POST') {
    const b = await body(req);
    const email = normEmail(b.email), name = String(b.name || '').trim().slice(0, 60), pw = String(b.password || '');
    if (!validEmail(email)) return json(req, { error: 'Adresse e-mail invalide.' }, 400);
    if (pw.length < 8 || pw.length > 200) return json(req, { error: 'Mot de passe : 8 caractères minimum.' }, 400);
    if (await env.DATA.get('acct:' + email)) return json(req, { error: 'Un compte existe déjà avec cette adresse.' }, 409);
    const salt = randHex(16);
    const a = { email, name, salt, hash: await hashPw(pw, salt), status: email === admin ? 'approved' : 'pending', created: Date.now() };
    await env.DATA.put('acct:' + email, JSON.stringify(a));
    return json(req, { ok: true, status: a.status });
  }

  if (path === '/api/login' && req.method === 'POST') {
    const b = await body(req);
    const email = normEmail(b.email), pw = String(b.password || '');
    const fails = +(await env.DATA.get('fail:' + email) || 0);
    if (fails >= 10) return json(req, { error: 'Trop d’essais. Réessaie dans 15 minutes.' }, 429);
    const a = await getJ(env, 'acct:' + email);
    const ok = a && sameStr(await hashPw(pw, a.salt), a.hash);
    if (!ok) {
      await env.DATA.put('fail:' + email, String(fails + 1), { expirationTtl: 900 });
      return json(req, { error: 'E-mail ou mot de passe incorrect.' }, 401);
    }
    if (a.status === 'pending') return json(req, { error: 'Ton compte attend la validation de l’administrateur.', status: 'pending' }, 403);
    if (a.status !== 'approved') return json(req, { error: 'Ce compte n’a pas été accepté.', status: a.status }, 403);
    const token = randHex(32);
    await env.DATA.put('sess:' + token, email, { expirationTtl: SESSION_TTL });
    await env.DATA.delete('fail:' + email);
    return json(req, { token, user: pub(a, env) });
  }

  const s = await session(req, env);
  if (!s) return json(req, { error: 'Non connecté.' }, 401);
  const me = s.acct;

  if (path === '/api/me' && req.method === 'GET') return json(req, { user: pub(me, env) });

  if (path === '/api/logout' && req.method === 'POST') { await env.DATA.delete('sess:' + s.token); return json(req, { ok: true }); }

  if (path === '/api/password' && req.method === 'POST') {
    const b = await body(req);
    if (!sameStr(await hashPw(String(b.old || ''), me.salt), me.hash)) return json(req, { error: 'Ancien mot de passe incorrect.' }, 400);
    const pw = String(b.password || '');
    if (pw.length < 8 || pw.length > 200) return json(req, { error: 'Mot de passe : 8 caractères minimum.' }, 400);
    me.salt = randHex(16); me.hash = await hashPw(pw, me.salt);
    await env.DATA.put('acct:' + me.email, JSON.stringify(me));
    return json(req, { ok: true });
  }

  if (path === '/api/data') {
    const k = 'data:' + me.email;
    if (req.method === 'GET') return json(req, { email: me.email, data: await getJ(env, k) });
    if (req.method === 'PUT') {
      const t = await req.text();
      if (t.length > MAX_DATA) return json(req, { error: 'Données trop volumineuses.' }, 413);
      try { JSON.parse(t); } catch (e) { return json(req, { error: 'Format invalide.' }, 400); }
      await env.DATA.put(k, t);
      return json(req, { ok: true, size: t.length });
    }
  }

  if (path.startsWith('/api/admin/')) {
    if (me.email !== admin) return json(req, { error: 'Réservé à l’administrateur.' }, 403);
    if (path === '/api/admin/users' && req.method === 'GET') {
      const out = []; let cursor;
      do {
        const l = await env.DATA.list({ prefix: 'acct:', cursor });
        for (const k of l.keys) { const a = await getJ(env, k.name); if (a) out.push(pub(a, env)); }
        cursor = l.list_complete ? null : l.cursor;
      } while (cursor);
      out.sort((a, b) => (a.status === 'pending' ? 0 : 1) - (b.status === 'pending' ? 0 : 1) || b.created - a.created);
      return json(req, { users: out });
    }
    if (path === '/api/admin/user' && req.method === 'POST') {
      const b = await body(req);
      const email = normEmail(b.email);
      if (email === admin) return json(req, { error: 'Impossible de modifier le compte administrateur.' }, 400);
      const a = await getJ(env, 'acct:' + email);
      if (!a) return json(req, { error: 'Compte introuvable.' }, 404);
      if (b.action === 'approve') { a.status = 'approved'; a.approvedAt = Date.now(); }
      else if (b.action === 'refuse') a.status = 'refused';
      else if (b.action === 'delete') { await env.DATA.delete('acct:' + email); await env.DATA.delete('data:' + email); return json(req, { ok: true }); }
      else return json(req, { error: 'Action inconnue.' }, 400);
      await env.DATA.put('acct:' + email, JSON.stringify(a));
      return json(req, { ok: true, user: pub(a, env) });
    }
  }
  return json(req, { error: 'Introuvable.' }, 404);
}

export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    if (url.pathname.startsWith('/api/')) {
      try { return await api(req, env, url.pathname); }
      catch (e) { return json(req, { error: 'Erreur serveur.' }, 500); }
    }
    return env.ASSETS.fetch(req);
  }
};
