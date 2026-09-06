// 백엔드(/api/*) 호출 래퍼
const Api = {
  async bodyAge(payload) {
    return post('/api/bodyage', payload);
  },
  async target(payload) {
    return post('/api/target', payload);
  },
  async dailyPrescription(payload) {
    return post('/api/daily-prescription', payload);
  },
  async intensity(daysSinceStart) {
    return get(`/api/intensity?daysSinceStart=${daysSinceStart}`);
  },
  async videos(params) {
    const qs = new URLSearchParams(Object.entries(params).filter(([, v]) => v != null && v !== ''));
    return get(`/api/videos?${qs.toString()}`);
  },
  async centers(lat, lon, limit = 5) {
    const qs = new URLSearchParams();
    if (lat != null) qs.set('lat', lat);
    if (lon != null) qs.set('lon', lon);
    qs.set('limit', limit);
    return get(`/api/centers?${qs.toString()}`);
  },
  async prescriptions(factor) {
    return get(`/api/prescriptions?factor=${encodeURIComponent(factor)}`);
  },
};

async function get(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`GET ${url} 실패 (${res.status})`);
  return res.json();
}
async function post(url, body) {
  const res = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  if (!res.ok) throw new Error(`POST ${url} 실패 (${res.status})`);
  return res.json();
}
