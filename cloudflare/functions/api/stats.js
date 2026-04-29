/**
 * GET /api/stats?campaign=erasmus|sal_shikum_tovplay|sal_shikum_tovtech
 * Returns campaign statistics from Firebase.
 *
 * Campaign routing:
 *   erasmus (default)    → stats/global, stats_daily/{date}, events
 *   sal_shikum_tovplay   → sal_shikum_tovplay_stats/global, ...
 *   sal_shikum_tovtech   → sal_shikum_tovtech_stats/global, ...
 */

import { initDB } from '../_lib/firebase.js'

const CORS = { 'Access-Control-Allow-Origin': '*', 'Content-Type': 'application/json' }

// Campaign-specific collection names
const CAMPAIGN_COLLECTIONS = {
  erasmus:             { stats: 'stats/global',                        daily: 'stats_daily',                        events: 'events' },
  sal_shikum_tovplay:  { stats: 'sal_shikum_tovplay_stats/global',     daily: 'sal_shikum_tovplay_stats_daily',     events: 'sal_shikum_tovplay_events' },
  sal_shikum_tovtech:  { stats: 'sal_shikum_tovtech_stats/global',     daily: 'sal_shikum_tovtech_stats_daily',     events: 'sal_shikum_tovtech_events' },
}

export async function onRequestGet({ request, env }) {
  try {
    const db = await initDB(env)
    const url = new URL(request.url)
    const campaign = url.searchParams.get('campaign') || 'erasmus'
    const cols = CAMPAIGN_COLLECTIONS[campaign] || CAMPAIGN_COLLECTIONS.erasmus

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
