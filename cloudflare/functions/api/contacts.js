/**
 * GET /api/contacts?campaign=main|my_campaign&tier=Tier1&status=replied&limit=200
 * Returns contact list from Firebase with optional filters.
 *
 * Campaign routing:
 *   main (default)   → contacts collection
 *   my_campaign      → my_campaign collection (named after the campaign)
 *
 * To add a new campaign collection: add an entry to CAMPAIGN_COLLECTION below.
 */

import { initDB } from '../_lib/firebase.js'

const CORS = { 'Access-Control-Allow-Origin': '*', 'Content-Type': 'application/json' }

// Maps campaign name → Firestore collection name.
// Add entries here when you create new campaigns.
const CAMPAIGN_COLLECTION = {
  main: 'contacts',
  // Example: add your custom campaign below:
  // my_campaign: 'my_campaign',
}

export async function onRequestGet({ request, env }) {
  try {
    const url      = new URL(request.url)
    const campaign = url.searchParams.get('campaign') || 'main'
    const tier     = url.searchParams.get('tier')
    const status   = url.searchParams.get('status')
    const limit    = parseInt(url.searchParams.get('limit') || '200')

    const db = await initDB(env)

    const replied    = url.searchParams.get('replied')
    const collection = CAMPAIGN_COLLECTION[campaign] || 'contacts'

    const filters = []
    if (tier)    filters.push(['tier',   '==', tier])
    if (status)  filters.push(['status', '==', status])
    if (replied) filters.push(['replied', '==', replied === 'true'])

    const contacts = await db.query(collection, filters, { limit })

    // Sort: Tier1 → Tier2 → Tier3, replied first
    const tierOrder = { Tier1: 1, Tier2: 2, Tier3: 3 }
    contacts.sort((a, b) => {
      const td = (tierOrder[a.tier] || 9) - (tierOrder[b.tier] || 9)
      if (td !== 0) return td
      if (a.replied_at && !b.replied_at) return -1
      if (!a.replied_at && b.replied_at) return  1
      return 0
    })

    return new Response(JSON.stringify(contacts), { headers: CORS })

  } catch (e) {
    return new Response(JSON.stringify({ error: e.message }), { status: 500, headers: CORS })
  }
}

export async function onRequestOptions() {
  return new Response(null, { headers: CORS })
}
