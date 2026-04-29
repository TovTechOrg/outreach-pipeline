/**
 * GET /api/stats?campaign=main|my_campaign
 * Returns campaign statistics from Firebase.
 *
 * Campaign routing:
 *   main (default)   → stats/global, stats_daily/{date}, events
 *   my_campaign      → my_campaign_stats/global, my_campaign_stats_daily, my_campaign_events
 *
 * To add a new campaign: add an entry to CAMPAIGN_COLLECTIONS below,
 * following the naming pattern. Then redeploy the dashboard.
 */

import { initDB } from '../_lib/firebase.js'

const CORS = { 'Access-Control-Allow-Origin': '*', 'Content-Type': 'application/json' }

// Campaign-specific collection names.
// Add entries here when you create new campaigns.
// Pattern: { stats: '<campaign>_stats/global', daily: '<campaign>_stats_daily', events: '<campaign>_events' }
const CAMPAIGN_COLLECTIONS = {
  main: { stats: 'stats/global', daily: 'stats_daily', events: 'events' },
  // Example: add your custom campaign below:
  // my_campaign: { stats: 'my_campaign_stats/global', daily: 'my_campaign_stats_daily', events: 'my_campaign_events' },
}

export async function onRequestGet({ request, env }) {
  try {
    const db = await initDB(env)
    const url = new URL(request.url)
    const campaign = url.searchParams.get('campaign') || 'main'
    const cols = CAMPAIGN_COLLECTIONS[campaign] || CAMPAIGN_COLLECTIONS.main

    // 1. Global totals (1 read — maintained by step6)
    const global = await db.get(cols.stats) || {
      total: 0, sent: 0, pending: 0, replied: 0, clicked: 0, bounced: 0,
      initial_sent: 0, followup1_sent: 0, followup2_sent: 0,
      by_tier: {},
    }

    // 2. Daily stats for last 30 days (up to 30 reads)
    const days = []
    for (let i = 29; i >= 0; i--) {
      const d = new Date()
      d.setUTCDate(d.getUTCDate() - i)
      days.push(d.toISOString().slice(0, 10))
    }

    const dailyDocs = await Promise.all(
      days.map(day => db.get(`${cols.daily}/${day}`))
    )
    const daily = days.flatMap((day, i) => {
      const doc = dailyDocs[i]
      if (!doc) return []
      return ['initial_sent', 'followup1_sent', 'followup2_sent', 'replied', 'clicked', 'bounced']
        .filter(t => doc[t] > 0)
        .map(t => ({ day, event_type: t, n: doc[t] }))
    })

    // 3. Recent activity (last 20 events, ordered by created_at desc)
    const recent = await db.query(cols.events, [], { orderBy: 'created_at', limit: 20 })

    // 4. Available campaigns list (always returned)
    const campaigns = Object.keys(CAMPAIGN_COLLECTIONS)

    return new Response(JSON.stringify({
      campaign,
      campaigns,
      totals:  global,
      by_tier: global.by_tier || {},
      daily,
      recent,
      as_of:   new Date().toISOString(),
    }), { headers: CORS })

  } catch (e) {
    return new Response(JSON.stringify({ error: e.message }), { status: 500, headers: CORS })
  }
}

export async function onRequestOptions() {
  return new Response(null, { headers: CORS })
}
