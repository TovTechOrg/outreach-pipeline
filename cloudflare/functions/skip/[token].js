/**
 * GET /skip/:token
 * Marks a pending AI reply draft as skipped (do nothing).
 * Called when Raz clicks the "Skip" link in the notification email.
 */
import { initDB } from '../_lib/firebase.js'

export async function onRequestGet({ params, env }) {
  const token = params.token

  try {
    const db  = await initDB(env)
    const doc = await db.get(`pending_replies/${token}`)

    if (!doc) {
      return htmlResponse('Not found', 'This link is invalid or has expired.', 404)
    }

    if (doc.status === 'sent') {
      return htmlResponse('Already sent', `The reply to ${doc.org_name} was already sent.`, 200)
    }

    await db.update(`pending_replies/${token}`, {
      status:     'skipped',
      skipped_at: new Date().toISOString(),
    })

    return htmlResponse(
      'Skipped',
      `Reply to <strong>${doc.org_name}</strong> has been skipped.<br>
       No email will be sent. You can reply manually from Gmail if needed.`,
      200
    )
  } catch (e) {
    console.error('Skip error:', e.message)
    return htmlResponse('Error', e.message, 500)
  }
}

function htmlResponse(title, body, status) {
  return new Response(
    `<!DOCTYPE html><html><head><meta charset="utf-8">
     <title>${title} — Outreach Pipeline</title>
     <style>body{font-family:Arial,sans-serif;max-width:600px;margin:60px auto;color:#222;line-height:1.6}
     h1{color:#2563eb}</style>
     </head><body><h1>${title}</h1><p>${body}</p></body></html>`,
    { status, headers: { 'Content-Type': 'text/html;charset=utf-8' } }
  )
}
