/**
 * Cloudflare Pages _worker.js — entry point (advanced mode)
 *
 * Routes:
 *   GET  /api/stats          → functions/api/stats.js       (auth required)
 *   GET  /api/contacts       → functions/api/contacts.js    (auth required)
 *   GET  /track/c/:token     → functions/track/c/[token].js (public — email links)
 *   GET  /approve/:token     → functions/approve/[token].js (public — AI reply approval)
 *   GET  /skip/:token        → functions/skip/[token].js    (public — AI reply skip)
 *   POST /webhook/gmail      → functions/webhook/gmail.js   (public — Google Pub/Sub)
 *   *    *                   → env.ASSETS (static files)    (auth required)
 *
 * Security:
 *   HTTP Basic Auth on all routes except /track/c/*, /approve/*, /skip/*, and /webhook/gmail.
 *   Set DASHBOARD_PASSWORD secret in Cloudflare Pages dashboard.
 *   Username is "admin" (or override with DASHBOARD_USER secret).
 */

import { onRequestGet as getStats }     from './functions/api/stats.js'
import { onRequestGet as getContacts }  from './functions/api/contacts.js'
import { onRequestGet as getToken }     from './functions/track/c/[token].js'
import { onRequestPost as postWebhook } from './functions/webhook/gmail.js'
import { onRequestGet as approveReply } from './functions/approve/[token].js'
import { onRequestGet as skipReply }    from './functions/skip/[token].js'

const CORS = { 'Access-Control-Allow-Origin': '*', 'Content-Type': 'application/json' }

// Routes that bypass auth (public-facing)
function isPublicRoute(path, method) {
  if (path.startsWith('/track/c/'))   return true   // email click links
  if (path.startsWith('/approve/'))   return true   // AI reply approval
  if (path.startsWith('/skip/'))      return true   // AI reply skip
  if (path === '/webhook/gmail' && method === 'POST') return true  // Google Pub/Sub
  return false
}

function requiresAuth(env) {
  return !!env.DASHBOARD_PASSWORD
}

function checkBasicAuth(request, env) {
  const authHeader = request.headers.get('Authorization') || ''
  if (!authHeader.startsWith('Basic ')) return false

  let decoded
  try {
    decoded = atob(authHeader.slice(6))
  } catch {
    return false
  }

  const colon = decoded.indexOf(':')
  if (colon === -1) return false

  const user     = decoded.slice(0, colon)
  const password = decoded.slice(colon + 1)

  const expectedUser = (env.DASHBOARD_USER || 'admin').trim()
  const expectedPass = env.DASHBOARD_PASSWORD.trim()

  // Constant-time comparison to prevent timing attacks
  const userMatch = user.length === expectedUser.length &&
    [...user].every((c, i) => c === expectedUser[i])
  const passMatch = password.length === expectedPass.length &&
    [...password].every((c, i) => c === expectedPass[i])

  return userMatch && passMatch
}

function unauthorizedResponse() {
  return new Response('Unauthorized', {
    status: 401,
    headers: {
      'WWW-Authenticate': 'Basic realm="Outreach Dashboard"',
      'Content-Type': 'text/plain',
    },
  })
}

export default {
  async fetch(request, env, ctx) {
    const url    = new URL(request.url)
    const path   = url.pathname
    const method = request.method

    // CORS preflight — always allow
    if (method === 'OPTIONS') {
      return new Response(null, { headers: CORS })
    }

    // Enforce auth on protected routes
    if (!isPublicRoute(path, method) && requiresAuth(env)) {
      if (!checkBasicAuth(request, env)) {
        return unauthorizedResponse()
      }
    }

    // Build context object compatible with Pages Functions format
    const context = {
      request,
      env,
      params: {},
      waitUntil: (p) => ctx.waitUntil(p),
    }

    if (path === '/api/stats' && method === 'GET') {
      return getStats(context)
    }

    if (path === '/api/contacts' && method === 'GET') {
      return getContacts(context)
    }

    // /track/c/:token
    const tokenMatch = path.match(/^\/track\/c\/([^/]+)$/)
    if (tokenMatch && method === 'GET') {
      context.params = { token: tokenMatch[1] }
      return getToken(context)
    }

    // /approve/:token — AI reply approval
    const approveMatch = path.match(/^\/approve\/([^/]+)$/)
    if (approveMatch && method === 'GET') {
      context.params = { token: approveMatch[1] }
      return approveReply(context)
    }

    // /skip/:token — AI reply skip
    const skipMatch = path.match(/^\/skip\/([^/]+)$/)
    if (skipMatch && method === 'GET') {
      context.params = { token: skipMatch[1] }
      return skipReply(context)
    }

    if (path === '/webhook/gmail' && method === 'POST') {
      return postWebhook(context)
    }

    // Serve static assets (index.html, etc.)
    return env.ASSETS.fetch(request)
  },
}
