/**
 * POST /webhook/gmail
 * Receives Gmail Push Notifications from Google Cloud Pub/Sub.
 *
 * When Gmail detects inbox activity, Pub/Sub pushes here immediately.
 * We then check active threads for replies and mark them in Firebase.
 *
 * Setup (one-time):
 *   1. Google Cloud Console → Pub/Sub → Create topic
 *   2. Grant gmail-api-push@system.gserviceaccount.com "Pub/Sub Publisher" on the topic
 *   3. Create push subscription → endpoint: https://your-pages.pages.dev/webhook/gmail
 *   4. Run setup_gmail_watch.py to register the Gmail watch
 *
 * Environment variables needed:
 *   FIREBASE_SA, FIREBASE_PROJECT (same as other functions)
 *   GMAIL_TOKEN   — the OAuth token JSON for reply checking
 *                   (or handle via step6 daily — this is the real-time bonus)
 */

import { initDB } from '../_lib/firebase.js'

export async function onRequestPost({ request, env }) {
  // Always return 200 immediately — Pub/Sub retries if it gets anything else
  const respond200 = new Response('OK', { status: 200 })

  try {
    const body = await request.json()
    const data = body?.message?.data

    if (!data) return respond200

    // Decode base64 Pub/Sub payload
    const decoded = JSON.parse(atob(data))
    // Gmail sends: { "emailAddress": "raz@...", "historyId": "12345" }

    if (decoded.historyId) {
      // Non-blocking — check replies in background
      env.ctx?.waitUntil(checkReplies(env, decoded.historyId))
    }

  } catch (e) {
    console.error('Webhook error:', e.message)
  }

  return respond200
}

async function checkReplies(env, historyId) {
  if (!env.GMAIL_TOKEN) return  // Gmail token not configured — skip

  try {
    const db          = await initDB(env)
    const gmailToken  = JSON.parse(env.GMAIL_TOKEN)
    const accessToken = gmailToken.access_token

    // Get all contacts with active threads (not yet replied)
    const active = await db.query('contacts', [
      ['replied', '==', false],
    ], { limit: 500 })

    const threadsToCheck = active.filter(c =>
      c.followup1_thread_id || c.initial_thread_id
    )

    for (const contact of threadsToCheck) {
      const threadId = contact.followup1_thread_id || contact.initial_thread_id
      const hasReply = await checkThread(accessToken, threadId)

      if (hasReply) {
        const now   = new Date().toISOString()
        const today = now.slice(0, 10)
        const docId = safeId(contact.org_name)

        await Promise.all([
          db.update(`contacts/${docId}`, {
            status:     'replied',
            replied:    true,
            replied_at: now,
          }),
          db.add('events', {
            org_name:   contact.org_name,
            event_type: 'replied',
            event_data: JSON.stringify({ thread_id: threadId, via: 'webhook' }),
            created_at: now,
          }),
          db.increment(`stats_daily/${today}`, 'replied'),
          db.increment('stats/global', 'replied'),
        ])

        console.log(`[Webhook] Reply detected: ${contact.org_name}`)
      }
    }
  } catch (e) {
    console.error('Reply check error:', e.message)
  }
}

async function checkThread(accessToken, threadId) {
  try {
    const res = await fetch(
      `https://gmail.googleapis.com/gmail/v1/users/me/threads/${threadId}?format=minimal`,
      { headers: { Authorization: `Bearer ${accessToken}` } }
    )
    const data = await res.json()
    return (data.messages?.length || 0) > 1
  } catch {
    return false
  }
}

function safeId(s) {
  return s.replace(/[^\w-]/g, '_').slice(0, 100)
}
