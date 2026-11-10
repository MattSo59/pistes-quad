/* Service worker — Pistes Quad & SSV
   - Coque de l'appli : servie depuis le cache, mise à jour en arrière-plan
   - Tuiles de carte : cache d'abord (hors-ligne), limité en nombre
   - Données (Overpass, géocodage, altitude) : réseau uniquement (l'appli les garde elle-même) */
const SHELL_CACHE = 'pq-shell-v29';
const TILE_CACHE = 'pq-tiles';
const MAX_TILES = 8000;
const SHELL = [
  './', './index.html', './manifest.webmanifest', './icon-192.png', './icon-512.png', './apple-touch-icon.png',
  'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css',
  'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js'
];
const TILE_RE = /data\.geopf\.fr\/(private\/)?wmts|tile\.openstreetmap\.org|tile\.opentopomap\.org/;
const NET_ONLY_RE = /overpass|geocodage|altimetrie|interpreter|nominatim|\/data\/|\/api\/|cdn-cgi|cloudflareaccess|\.pdf(\?|$)/;

self.addEventListener('install', e => {
  e.waitUntil((async () => {
    const c = await caches.open(SHELL_CACHE);
    await Promise.all(SHELL.map(u => corsOrNoCors(u).then(r => r && c.put(u, r)).catch(() => {})));
    await self.skipWaiting();
  })());
});

self.addEventListener('activate', e => {
  e.waitUntil((async () => {
    const keys = await caches.keys();
    await Promise.all(keys.filter(k => k !== SHELL_CACHE && k !== TILE_CACHE).map(k => caches.delete(k)));
    await self.clients.claim();
  })());
});

// Essaie en CORS (réponse lisible, mise en cache légère) puis en no-cors
async function corsOrNoCors(url) {
  try { const r = await fetch(url, { mode: 'cors', credentials: 'omit' }); if (r.ok) return r; } catch (e) {}
  try { return await fetch(url, { mode: 'no-cors' }); } catch (e) { return null; }
}

let putCount = 0;
async function trimTiles(c) {
  if (++putCount % 300) return;
  const keys = await c.keys();
  if (keys.length > MAX_TILES) for (const k of keys.slice(0, keys.length - MAX_TILES)) await c.delete(k);
}

self.addEventListener('fetch', e => {
  const req = e.request;
  if (req.method !== 'GET') return;
  const url = req.url;
  if (NET_ONLY_RE.test(url)) return;

  if (TILE_RE.test(url)) {
    e.respondWith((async () => {
      const c = await caches.open(TILE_CACHE);
      const hit = await c.match(url);
      if (hit) return hit;
      try {
        const r = await fetch(url, { mode: 'cors', credentials: 'omit' });
        if (r.ok) { c.put(url, r.clone()).then(() => trimTiles(c)).catch(() => {}); }
        return r;
      } catch (err) {
        try { return await fetch(req); } catch (e2) { return Response.error(); }
      }
    })());
    return;
  }

  const sameOrigin = url.startsWith(self.location.origin);
  if (sameOrigin || url.startsWith('https://unpkg.com/leaflet')) {
    e.respondWith((async () => {
      const c = await caches.open(SHELL_CACHE);
      const key = sameOrigin ? url.split('#')[0].split('?')[0] : url;
      const appPage = req.mode === 'navigate' && /\/(index\.html)?$/.test(key);
      const hit = await c.match(key) || (appPage ? await c.match('./index.html') : null);
      const net = fetch(req).then(r => { if (r && (r.ok || r.type === 'opaque')) c.put(key, r.clone()).catch(() => {}); return r; }).catch(() => null);
      if (hit) { e.waitUntil(net); return hit; }
      return (await net) || Response.error();
    })());
  }
});

self.addEventListener('message', e => { if (e.data === 'skipWaiting') self.skipWaiting(); });
