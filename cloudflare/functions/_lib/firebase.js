/**
 * Firestore REST API client for Cloudflare Workers.
 *
 * Environment variables required (set in Cloudflare Pages dashboard):
 *   FIREBASE_SA      — service account JSON (full contents, as a string secret)
 *   FIREBASE_PROJECT — Firebase project ID (e.g. "my-outreach-project")
 */

const FIRESTORE = (pid) =>
  `https://firestore.googleapis.com/v1/projects/${pid}/databases/(default)/documents`

// ── Auth ──────────────────────────────────────────────────────────────────────

export async function getAccessToken(sa) {
  const now = Math.floor(Date.now() / 1000)

  const b64url = (obj) =>
    btoa(JSON.stringify(obj))
      .replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')

  const header  = b64url({ alg: 'RS256', typ: 'JWT' })
  const payload = b64url({
    iss: sa.client_email,
    sub: sa.client_email,
    aud: 'https://oauth2.googleapis.com/token',
    iat: now, exp: now + 3600,
    scope: 'https://www.googleapis.com/auth/datastore',
  })

  const keyBytes = Uint8Array.from(
    atob(sa.private_key.replace(/-----[^-]+-----|\\n|\n/g, '')),
    c => c.charCodeAt(0)
  )
  const key = await crypto.subtle.importKey(
    'pkcs8', keyBytes,
    { name: 'RSASSA-PKCS1-v1_5', hash: 'SHA-256' },
    false, ['sign']
  )
  const sigBytes = await crypto.subtle.sign(
    'RSASSA-PKCS1-v1_5', key,
    new TextEncoder().encode(`${header}.${payload}`)
  )
  const sig = btoa(String.fromCharCode(...new Uint8Array(sigBytes)))
    .replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')

  const res = await fetch('https://oauth2.googleapis.com/token', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: `grant_type=urn%3Aietf%3Aparams%3Aoauth%3Agrant-type%3Ajwt-bearer&assertion=${header}.${payload}.${sig}`,
  })
  const rawText = await res.text()
  let data
  try { data = JSON.parse(rawText) } catch { throw new Error(`OAuth2 non-JSON (${res.status}): ${rawText.slice(0, 300)}`) }
  if (!data.access_token) throw new Error(`Auth failed (${res.status}): ${JSON.stringify(data)}`)
  return data.access_token
}

// ── Firestore value serialization ─────────────────────────────────────────────

function unwrap(v) {
  if ('stringValue'    in v) return v.stringValue
  if ('integerValue'   in v) return parseInt(v.integerValue)
  if ('doubleValue'    in v) return v.doubleValue
  if ('booleanValue'   in v) return v.booleanValue
  if ('nullValue'      in v) return null
  if ('timestampValue' in v) return v.timestampValue
  if ('mapValue'       in v) return fields2obj(v.mapValue.fields || {})
  if ('arrayValue'     in v) return (v.arrayValue.values || []).map(unwrap)
  return null
}

function wrap(val) {
  if (val === null || val === undefined) return { nullValue: null }
  if (typeof val === 'boolean') return { booleanValue: val }
  if (typeof val === 'number')  return Number.isInteger(val)
    ? { integerValue: String(val) }
    : { doubleValue: val }
  if (typeof val === 'string')  return { stringValue: val }
  if (Array.isArray(val))       return { arrayValue: { values: val.map(wrap) } }
  if (typeof val === 'object')  return { mapValue: { fields: obj2fields(val) } }
  return { stringValue: String(val) }
}

const fields2obj = (fields) =>
  Object.fromEntries(Object.entries(fields).map(([k, v]) => [k, unwrap(v)]))

const obj2fields = (obj) =>
  Object.fromEntries(
    Object.entries(obj)
      .filter(([, v]) => v !== undefined)
      .map(([k, v]) => [k, wrap(v)])
  )

// ── Firestore DB class ────────────────────────────────────────────────────────

export class DB {
  constructor(projectId, token) {
    this.base = FIRESTORE(projectId)
    this.h    = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }
  }

  async get(path) {
    const r = await fetch(`${this.base}/${path}`, { headers: this.h })
    if (r.status === 404) return null
    const text = await r.text()
    let d
    try { d = JSON.parse(text) } catch { throw new Error(`Firestore get(${path}) non-JSON (${r.status}): ${text.slice(0, 200)}`) }
    if (!d.fields) return null
    return { _id: path.split('/').pop(), ...fields2obj(d.fields) }
  }

  async set(path, data) {
    await fetch(`${this.base}/${path}`, {
      method: 'PATCH', headers: this.h,
      body: JSON.stringify({ fields: obj2fields(data) }),
    })
  }

  async update(path, fields) {
    const mask = Object.keys(fields)
      .map(f => `updateMask.fieldPaths=${encodeURIComponent(f)}`).join('&')
    await fetch(`${this.base}/${path}?${mask}`, {
      method: 'PATCH', headers: this.h,
      body: JSON.stringify({ fields: obj2fields(fields) }),
    })
  }

  async add(collection, data) {
    await fetch(`${this.base}/${collection}`, {
      method: 'POST', headers: this.h,
      body: JSON.stringify({ fields: obj2fields(data) }),
    })
  }

  async query(collection, filters = [], { orderBy, limit = 200 } = {}) {
    const where = filters.length === 0 ? undefined :
      filters.length === 1
        ? { fieldFilter: mkFilter(filters[0]) }
        : { compositeFilter: { op: 'AND', filters: filters.map(f => ({ fieldFilter: mkFilter(f) })) } }

    const structuredQuery = {
      from: [{ collectionId: collection }],
      limit,
      ...(where   ? { where }   : {}),
      ...(orderBy ? { orderBy: [{ field: { fieldPath: orderBy }, direction: 'DESCENDING' }] } : {}),
    }

    const r = await fetch(
      `${this.base}:runQuery`,
      { method: 'POST', headers: this.h, body: JSON.stringify({ structuredQuery }) }
    )
    const text = await r.text()
    let rows
    try { rows = JSON.parse(text) }
    catch { throw new Error(`Firestore query(${collection}) ${r.status}: ${text.slice(0, 200)}`) }
    if (!Array.isArray(rows)) throw new Error(`Firestore query bad response: ${JSON.stringify(rows).slice(0, 200)}`)
    return rows
      .filter(row => row.document)
      .map(row => ({
        _id: row.document.name.split('/').pop(),
        ...fields2obj(row.document.fields || {}),
      }))
  }

  // Atomic increment via Firestore commit + field transform
  async increment(path, field, amount = 1) {
    const docName = this.base.replace('https://firestore.googleapis.com/v1/', '') + `/${path}`
    await fetch(`${this.base}:commit`, {
      method: 'POST', headers: this.h,
      body: JSON.stringify({
        writes: [{
          transform: {
            document: docName,
            fieldTransforms: [{ fieldPath: field, increment: { integerValue: String(amount) } }],
          },
        }],
      }),
    })
  }
}

const OP_MAP = {
  '==': 'EQUAL', '!=': 'NOT_EQUAL',
  '<': 'LESS_THAN', '<=': 'LESS_THAN_OR_EQUAL',
  '>': 'GREATER_THAN', '>=': 'GREATER_THAN_OR_EQUAL',
  'in': 'IN',
}

function mkFilter([field, op, value]) {
  return {
    field: { fieldPath: field },
    op:    OP_MAP[op] || op,
    value: wrap(value),
  }
}

// ── Factory ───────────────────────────────────────────────────────────────────

export async function initDB(env) {
  const sa    = JSON.parse(env.FIREBASE_SA)
  const token = await getAccessToken(sa)
  return new DB(env.FIREBASE_PROJECT.trim(), token)
}
