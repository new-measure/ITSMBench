#!/usr/bin/env node
'use strict';

const fs = require('fs');
const path = require('path');
const http = require('http');

const TESTS_DIR = process.env.TESTS_DIR || __dirname;
const ASSERTIONS_PATH = process.env.ASSERTIONS_PATH || path.join(TESTS_DIR, 'assertions.json');
const INITIAL_PATH = process.env.INITIAL_STATE_PATH || path.join(TESTS_DIR, 'initial_state.json');
const OUT_DIR = process.env.VERIFIER_OUT || '/logs/verifier';
const RESULT_JSON = path.join(OUT_DIR, 'judge_result.json');
const REWARD_TXT = path.join(OUT_DIR, 'reward.txt');
const MOCK_ADDR = process.env.MOCK_ADDR || '';
const DUMP_INITIAL = process.argv.includes('--dump-initial');

const READBACK = {
  vanta: {
    host: 'vanta.local.mock',
    collections: {
      vendors: {
        async fetch(getJson) {
          const all = [];
          let cursor = '';
          for (let guard = 0; guard < 200; guard++) {
            const q = cursor
              ? `/v1/vendors?pageSize=100&pageCursor=${encodeURIComponent(cursor)}`
              : '/v1/vendors?pageSize=100';
            const resp = await getJson(q);
            const data = (resp && resp.results && Array.isArray(resp.results.data)) ? resp.results.data : [];
            all.push(...data);
            const info = (resp && resp.results && resp.results.pageInfo) || {};
            if (!info.hasNextPage || !info.endCursor) break;
            cursor = info.endCursor;
          }
          return all;
        }
      }
    }
  }
};

function httpGetJson(appHost, pathWithQuery) {
  return new Promise((resolve, reject) => {
    let connHost = appHost;
    let connPort = 8080;
    if (MOCK_ADDR) {
      const [h, p] = MOCK_ADDR.split(':');
      connHost = h;
      connPort = Number(p || 8080);
    }
    const req = http.request({ host: connHost, port: connPort, path: pathWithQuery, method: 'GET', headers: { host: appHost } }, (res) => {
      let d = '';
      res.on('data', (c) => (d += c));
      res.on('end', () => {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          try { resolve(JSON.parse(d)); } catch (e) { reject(new Error(`bad JSON from ${appHost}${pathWithQuery}`)); }
        } else { const e = new Error(`HTTP ${res.statusCode} from ${appHost}${pathWithQuery}`); e.statusCode = res.statusCode; reject(e); }
      });
    });
    req.on('error', reject);
    req.end();
  });
}

function stateKey(a) {
  return `${a.app}::${a.collection}::${JSON.stringify(a.path_params || {})}`;
}

function fillPath(template, params) {
  return template.replace(/\{([^}]+)\}/g, (_, name) => {
    if (!params || params[name] === undefined) throw new Error(`missing path_param ${name}`);
    return encodeURIComponent(String(params[name]));
  });
}

async function fetchCollection(a) {
  const provider = READBACK[a.app];
  const spec = provider && provider.collections[a.collection];
  if (!spec) throw new Error(`no readback registered for ${a.app}.${a.collection}`);
  try {
    if (typeof spec.fetch === 'function') {
      const getJson = (p) => httpGetJson(provider.host, p);
      const records = await spec.fetch(getJson);
      return Array.isArray(records) ? records : [];
    }
    const data = await httpGetJson(provider.host, fillPath(spec.path, a.path_params));
    const records = spec.pick(data);
    return Array.isArray(records) ? records : [];
  } catch (e) {
    if (e.statusCode === 404 && a.path_params && Object.keys(a.path_params).length) return []; 
    throw e;
  }
}

async function buildFinalState(assertions) {
  const state = {};
  for (const a of assertions) {
    const key = stateKey(a);
    if (state[key] === undefined) state[key] = await fetchCollection(a);
  }
  return state;
}

const NEGATIVE_TYPES = new Set(['record_not_exists', 'field_not_equals']);
function isNegative(a) {
  if (a && a.negative === true) return true;
  if (NEGATIVE_TYPES.has(a.type)) return true;
  return /(_not_|_no_|_not$|not_exists)/i.test(a.type);
}
function normStr(v) { return v === undefined || v === null ? '' : String(v).trim(); }
function stripCommasInNumbers(s) { return String(s).replace(/(\d),(\d)/g, '$1$2'); }
function norm(v) {
  const s = stripCommasInNumbers(normStr(v).toLowerCase().replace(/^\$/, ''));
  const n = Number(s);
  return Number.isFinite(n) && s !== '' ? String(n) : s;
}
function eqLoose(a, b) { return norm(a) === norm(b); }
function containsLoose(h, n) { return norm(h).includes(norm(n)); }
function getPath(obj, dotted) {
  if (obj == null) return undefined;
  return String(dotted).split('.').reduce((o, k) => (o == null ? undefined : o[k]), obj);
}
function resolveCollection(state, a) {
  const raw = state ? state[stateKey(a)] : undefined;
  if (raw == null) return [];
  return (Array.isArray(raw) ? raw.slice() : Object.values(raw)).filter((r) => r && typeof r === 'object');
}
function recordMatches(record, a) {
  if (a.match && !Object.entries(a.match).every(([k, v]) => eqLoose(getPath(record, k), v))) return false;
  if (a.match_contains && !Object.entries(a.match_contains).every(([k, v]) => containsLoose(getPath(record, k), v))) return false;
  if (a.match_pattern && !Object.entries(a.match_pattern).every(([k, re]) => new RegExp(re, 'i').test(normStr(getPath(record, k))))) return false;
  return true;
}
function findMatches(state, a) { return resolveCollection(state, a).filter((r) => recordMatches(r, a)); }
const HANDLERS = {
  field_equals(state, a) { const r = findMatches(state, a)[0]; return r ? eqLoose(getPath(r, a.field), a.value) : false; },
  field_contains(state, a) { const r = findMatches(state, a)[0]; return r ? containsLoose(getPath(r, a.field), a.value) : false; },
  field_matches(state, a) { const r = findMatches(state, a)[0]; return r ? new RegExp(a.pattern, 'i').test(normStr(getPath(r, a.field))) : false; },
  field_not_equals(state, a) { const r = findMatches(state, a)[0]; return r ? !eqLoose(getPath(r, a.field), a.value) : true; },
  record_exists(state, a) { return findMatches(state, a).length > 0; },
  record_not_exists(state, a) { return findMatches(state, a).length === 0; },
  collection_count(state, a) {
    const list = a.match || a.match_contains || a.match_pattern ? findMatches(state, a) : resolveCollection(state, a);
    return list.length === Number(a.count);
  }
};
function checkOne(state, a) { const h = HANDLERS[a.type]; if (!h) throw new Error(`Unknown assertion type: ${a.type}`); return Boolean(h(state, a)); }
function safeCheck(state, a) { try { return checkOne(state, a); } catch (_) { return false; } }

function score(assertions, finalState, initialState) {
  const haveInitial = initialState != null;
  const evals = assertions.map((a) => {
    const neg = isNegative(a);
    const finalRes = checkOne(finalState, a);
    let counted; let passed; let excluded;
    if (a.scored === false) { counted = false; passed = finalRes; excluded = true; }
    else {
      const initialRes = haveInitial ? safeCheck(initialState, a) : false;
      const forceScored = a.excluded === false;
      if (haveInitial && initialRes && !forceScored) {
        if (!finalRes) { counted = true; passed = false; excluded = false; }
        else { counted = false; passed = true; excluded = true; }
      } else { counted = true; passed = finalRes; excluded = false; }
    }
    return { a, neg, counted, passed, excluded };
  });
  let total = 0; let passed = 0;
  const details = evals.map((e) => {
    const p = e.passed;
    if (e.counted) { total += 1; if (p) passed += 1; }
    const params = {}; for (const [k, v] of Object.entries(e.a)) if (k !== 'type') params[k] = v;
    return { type: e.a.type, negative: e.neg, counted: e.counted, excluded: e.excluded, passed: p, params };
  });
  return { partial: total > 0 ? passed / total : 0, binary: total > 0 && passed === total ? 1 : 0, passed, total, details };
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function buildFinalStateWithRetry(assertions, attempts = 3) {
  let lastErr;
  for (let attempt = 1; attempt <= attempts; attempt++) {
    try { return await buildFinalState(assertions); }
    catch (e) {
      lastErr = e;
      if (attempt < attempts) {
        console.error(`[grade] state read-back failed (attempt ${attempt}/${attempts}): ${e.message}; retrying`);
        await sleep(1000 * attempt);
      }
    }
  }
  throw lastErr;
}
function readJson(p) { return JSON.parse(fs.readFileSync(p, 'utf8')); }
function writeResult(s, binary, explanation, details) {
  fs.mkdirSync(OUT_DIR, { recursive: true });
  fs.writeFileSync(RESULT_JSON, `${JSON.stringify({ score: binary, partial_credit: Number(s.toFixed(4)), task_completed_correctly: binary, explanation, assertions: details || [] }, null, 2)}\n`);
  fs.writeFileSync(REWARD_TXT, `${binary}\n`);
}

function fail(m) {
  try {
    fs.mkdirSync(OUT_DIR, { recursive: true });
    fs.writeFileSync(RESULT_JSON, `${JSON.stringify({ error: m, score: null, task_completed_correctly: null, assertions: [] }, null, 2)}\n`);
  } catch (_) {  }
  console.error(`[grade] ERROR (no score emitted): ${m}`);
  process.exit(1);
}

async function main() {
  let assertions;
  try { const raw = readJson(ASSERTIONS_PATH); assertions = Array.isArray(raw) ? raw : raw.assertions || []; }
  catch (e) { return fail(`Could not read assertions: ${e.message}`); }
  if (!assertions.length) return fail('No assertions defined.');
  let finalState;
  try { finalState = await buildFinalStateWithRetry(assertions); } catch (e) { return fail(`Could not reconstruct final state: ${e.message}`); }
  if (DUMP_INITIAL) {
    fs.writeFileSync(INITIAL_PATH, `${JSON.stringify(finalState, null, 2)}\n`);
    console.log(`[grade] dumped initial state to ${INITIAL_PATH}`);
    return;
  }
  let initialState = null;
  try { if (fs.existsSync(INITIAL_PATH)) initialState = readJson(INITIAL_PATH); } catch (_) { initialState = null; }
  let result;
  try { result = score(assertions, finalState, initialState); } catch (e) { return fail(`Assertion error: ${e.message}`); }
  const explanation = `Passed ${result.passed}/${result.total} scored assertions (partial_credit=${result.partial.toFixed(3)}).`;
  writeResult(result.partial, result.binary, explanation, result.details);
  console.log(`[grade] ${explanation} task_completed_correctly=${result.binary}`);
}
main();
