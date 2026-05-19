/**
 * api-client.js — Shared API client for all O'Neil backtest dashboards.
 * Auto-detects host so both localhost and LAN (phone) access work.
 */
const API_BASE = 'http://' + window.location.hostname + ':8788';

async function apiFetch(path, opts = {}) {
  const url = API_BASE + path;
  const res = await fetch(url, { headers: { 'Content-Type': 'application/json' }, ...opts });
  if (!res.ok) throw new Error(`API ${res.status}: ${url}`);
  return res.json();
}

const API = {
  indices:       ()               => apiFetch('/api/indices'),
  kline:         (stock_code, start, end) => apiFetch(`/api/kline?stock_code=${stock_code}&start=${start}&end=${end}`),
  backtest:      (body)           => apiFetch('/api/backtest', { method: 'POST', body: JSON.stringify(body) }),
  save:          (body)           => apiFetch('/api/backtest/save', { method: 'POST', body: JSON.stringify(body) }),
  list:          ()               => apiFetch('/api/backtest/list'),
  compare:       (id1, id2)       => apiFetch(`/api/backtest/compare?id1=${id1}&id2=${id2}`),
  runSignals:    (run_id)         => apiFetch(`/api/backtest/${run_id}/signals`),
  loadConfig:    ()               => apiFetch('/api/config'),
  saveConfig:    (yamlStr)        => apiFetch('/api/config', { method: 'POST', body: yamlStr, headers: { 'Content-Type': 'text/plain' } }),
};
