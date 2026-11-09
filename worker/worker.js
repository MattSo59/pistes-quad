/* Pistes Quad – Worker Cloudflare : sert simplement l'appli (actifs statiques). */
export default { fetch: (request, env) => env.ASSETS.fetch(request) };
