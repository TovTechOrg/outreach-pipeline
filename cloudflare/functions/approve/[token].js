/**
 * GET /approve/:token
 * Marks a pending AI reply draft as approved.
 * Called when Raz clicks the "Approve & send" link in the notification email.
 */
import { initDB } from '../_lib/firebase.js'

export async function onRequestGet({ params, env }) {
  const token = params.token

  try {
    const db  = await initDB(env)
    const doc = await db.get(`pending_replies/${token}`)

    if (!doc) {
      return htmlResponse('Not found', 'This approval link is invalid or has expired.', 404)
    }

    if (doc.status === 'sent') {
      return htmlResponse('Already sent', `The reply to ${doc.org_name} was already sent.`, 200)
    }

    if (doc.status === 'skipped') {
      return htmlResponse('Skipped', `This reply was previously skipped.`, 200)
    }

    await db.update(`pending_replies/${token}`, {
      status:      'approved',
      approved_at: new Date().toISOString(),
    })

    return htmlResponse(
      'Approved!',
      `Reply to <strong>${doc.org_name}</strong> has been approved.<br>
       It will be sent on the next pipeline run (within 12 hours).<br><br>
       <em>Draft:</em><br><pre style="white-space:pre-wrap;font-size:13px">${esc(doc.ai_draft)}</pre>`,
      200
    )
  } catch (e) {
    console.error('Approve error:', e.message)
    return htmlResponse('Error', e.message, 500)
  }
}

function htmlResponse(title, body, status) {
  return new Response(
    `<!DOCTYPE html><html><head><meta charset="utf-8">
     <title>${title} — TovPlay Outreach</title>
     <style>body{font-family:Arial,sans-serif;max-width:600px;margin:60px auto;color:#222;line-height:1.6}
     h1{color:#2563eb}pre{background:#f3f4f6;padding:12px;border-radius:6px}</style>
     </head><body><h1>${title}</h1><p>${body}</p></body></html>`,
    { status, headers: { 'Content-Type': 'text/html;charset=utf-8' } }
  )
}

function esc(s = '') {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
}
