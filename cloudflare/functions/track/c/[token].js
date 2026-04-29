/**
 * GET /track/c/:token
 * Click tracking redirect.
 *
 * 1. Looks up token in Firebase
 * 2. Increments click_count on the contact + used_count on the token
 * 3. Logs a 'clicked' event
 * 4. Redirects to the target URL
 *
 * This URL is embedded in outreach emails. When a recipient clicks,
 * their browser hits this endpoint before being forwarded to the real URL.
 */

import { initDB } from '../../_lib/firebase.js'

export async function onRequestGet({ params, env, waitUntil }) {
  const token = params.token

  try {
    const db  = await initDB(env)
    const doc = await db.get(`tracking_tokens/${token}`)

    if (!doc || doc.token_type !== 'click') {
      return new Response('Link not found', { status: 404 })
    }

    const { org_name, target_url } = doc

    // Use waitUntil so the Worker stays alive to finish logging after the redirect
    waitUntil(logClick(db, token, org_name, target_url))

    return Response.redirect(target_url, 302)

  } catch (e) {
    // On any error still try to redirect gracefully if we have the token
    console.error('Click tracking error:', e.message)
    return new Response('Error', { status: 500 })
  }
}

async function logClick(db, token, org_name, target_url) {
  const today = new Date().toISOString().slice(0, 10)
  const now   = new Date().toISOString()

  await Promise.all([
    // Increment token use count
    db.increment(`tracking_tokens/${token}`, 'used_count'),

    // Increment contact click count
    db.increment(`contacts/${safeId(org_name)}`, 'click_count'),

    // Log event
    db.add('events', {
      org_name,
      event_type: 'clicked',
      event_data: JSON.stringify({ token, url: target_url }),
      created_at: now,
    }),

    // Update daily stats
    db.increment(`stats_daily/${today}`, 'clicked'),

    // Update global stats
    db.increment('stats/global', 'clicked'),
  ])
}

function safeId(s) {
  return s.replace(/[^\w-]/g, '_').slice(0, 100)
}
