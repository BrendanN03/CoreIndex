#!/usr/bin/env node
/**
 * Starts FastAPI + Vite on fixed ports (override with env if needed).
 * Default API 8010. Starts local dev_remote_factor_server on 8000 unless COREINDEX_DEV_FACTOR_STUB=0.
 * Default web 5173.
 * Run from repo root: npm run dev
 */
import net from 'node:net'
import fs from 'node:fs'
import { spawn } from 'node:child_process'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import process from 'node:process'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const repoRoot = path.resolve(__dirname, '..')
const apiDir = path.join(repoRoot, 'apps', 'api')
const webDir = path.join(repoRoot, 'apps', 'web')

function canBindPort(port) {
  return new Promise((resolve) => {
    const s = net.createServer()
    s.unref()
    s.once('error', () => resolve(false))
    s.listen(port, '127.0.0.1', () => {
      s.close(() => resolve(true))
    })
  })
}

function parsePort(name, fallback) {
  const raw = process.env[name]
  if (raw == null || raw === '') return fallback
  const n = Number.parseInt(String(raw), 10)
  if (!Number.isFinite(n) || n < 1 || n > 65535) {
    throw new Error(`Invalid ${name}=${raw} (want 1–65535)`)
  }
  return n
}

async function assertPortFree(port, label) {
  if (await canBindPort(port)) return
  console.error(
    `[dev-stack] ${label} port ${port} is already in use. Free it or set env ${label === 'API' ? 'COREINDEX_DEV_API_PORT' : 'COREINDEX_DEV_WEB_PORT'}.`,
  )
  console.error(`[dev-stack] Hint: lsof -iTCP:${port} -sTCP:LISTEN`)
  process.exit(1)
}

async function waitForApi(baseUrl, timeoutMs = 45000) {
  const url = `${baseUrl}/`
  const start = Date.now()
  while (Date.now() - start < timeoutMs) {
    const ac = new AbortController()
    const t = setTimeout(() => ac.abort(), 2000)
    try {
      const res = await fetch(url, { signal: ac.signal })
      if (res.ok) return
    } catch {
      /* retry */
    } finally {
      clearTimeout(t)
    }
    await new Promise((r) => setTimeout(r, 250))
  }
  throw new Error(`API did not respond at ${baseUrl} within ${timeoutMs / 1000}s`)
}

function pickPythonSync(apiRoot) {
  const venv = path.join(apiRoot, '.venv', 'bin', 'python3')
  const venvWin = path.join(apiRoot, '.venv', 'Scripts', 'python.exe')
  if (fs.existsSync(venv)) return venv
  if (fs.existsSync(venvWin)) return venvWin
  return 'python3'
}

/** Minimal .env parser (KEY=VAL). Shell env overrides file. */
function loadDotEnvFile(filePath) {
  const out = {}
  if (!fs.existsSync(filePath)) return out
  const text = fs.readFileSync(filePath, 'utf8')
  for (const line of text.split('\n')) {
    const trimmed = line.trim()
    if (!trimmed || trimmed.startsWith('#')) continue
    const eq = trimmed.indexOf('=')
    if (eq <= 0) continue
    const key = trimmed.slice(0, eq).trim()
    if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(key)) continue
    let val = trimmed.slice(eq + 1).trim()
    if (
      (val.startsWith('"') && val.endsWith('"')) ||
      (val.startsWith("'") && val.endsWith("'"))
    ) {
      val = val.slice(1, -1)
    }
    out[key] = val
  }
  return out
}

const children = []

function shutdown() {
  for (const c of children) {
    try {
      c.kill('SIGTERM')
    } catch {
      /* ignore */
    }
  }
}

process.on('SIGINT', () => {
  shutdown()
  process.exit(0)
})
process.on('SIGTERM', () => {
  shutdown()
  process.exit(0)
})

async function main() {
  const apiPort = parsePort('COREINDEX_DEV_API_PORT', 8010)
  const webPort = parsePort('COREINDEX_DEV_WEB_PORT', 5173)
  const factorStubPort = parsePort('COREINDEX_DEV_FACTOR_STUB_PORT', 8000)
  await assertPortFree(apiPort, 'API')
  await assertPortFree(webPort, 'Web')

  const python = pickPythonSync(apiDir)
  const proxyTarget = `http://127.0.0.1:${apiPort}`
  const apiEnvFile = loadDotEnvFile(path.join(apiDir, '.env'))

  console.log(`[dev-stack] API  → http://127.0.0.1:${apiPort}`)
  console.log(
    `[dev-stack] Judge chain (voucher + delivery ledger, not main web) → http://127.0.0.1:${apiPort}/judge-chain/`,
  )
  console.log(
    `[dev-stack] Web  → http://127.0.0.1:${webPort} (same as http://localhost:${webPort} on this machine)`,
  )
  console.log(`[dev-stack] Proxy /coreindex-api → ${proxyTarget}`)
  if (fs.existsSync(path.join(apiDir, '.env'))) {
    console.log('[dev-stack] Loaded apps/api/.env into API process (shell vars still override).')
  }
  console.log('')

  if (process.env.COREINDEX_DEV_FACTOR_STUB === '1') {
    if (await canBindPort(factorStubPort)) {
      const stub = spawn(
        python,
        [
          '-m',
          'uvicorn',
          'dev_remote_factor_server:app',
          '--host',
          '127.0.0.1',
          '--port',
          String(factorStubPort),
        ],
        {
          cwd: apiDir,
          stdio: 'inherit',
          env: { ...apiEnvFile, ...process.env, PYTHONUNBUFFERED: '1' },
        },
      )
      children.push(stub)
      stub.on('error', (err) => {
        console.error('[dev-stack] Factor stub failed to start:', err.message)
      })
      console.log(
        `[dev-stack] Factor stub → http://127.0.0.1:${factorStubPort} (dev_remote_factor_server; set COREINDEX_DEV_FACTOR_STUB=0 to skip if you forward CADO here)`,
      )
      await new Promise((r) => setTimeout(r, 500))
    } else {
      console.warn(
        `[dev-stack] Factor stub wanted but port ${factorStubPort} is in use — assuming SSH tunnel or another server (COREINDEX_DEV_FACTOR_STUB=0 skips this message next time).`,
      )
    }
  }
  console.log('')

  const uvicorn = spawn(
    python,
    [
      '-m',
      'uvicorn',
      'app.main:app',
      '--host',
      '0.0.0.0',
      '--port',
      String(apiPort),
    ],
    {
      cwd: apiDir,
      stdio: 'inherit',
      env: { ...apiEnvFile, ...process.env, PYTHONUNBUFFERED: '1' },
    },
  )
  children.push(uvicorn)

  uvicorn.on('error', (err) => {
    console.error('[dev-stack] Failed to start API:', err.message)
    console.error(
      '[dev-stack] Create venv: cd apps/api && python3 -m venv .venv && .venv/bin/pip install fastapi uvicorn pydantic pydantic-settings email-validator python-multipart python-dotenv requests',
    )
    shutdown()
    process.exit(1)
  })

  uvicorn.on('exit', (code, signal) => {
    if (signal === 'SIGTERM') return
    if (code && code !== 0) {
      console.error(`[dev-stack] API exited (${code})`)
      shutdown()
      process.exit(code ?? 1)
    }
  })

  try {
    await waitForApi(`http://127.0.0.1:${apiPort}`)
  } catch (e) {
    console.error('[dev-stack]', e.message)
    shutdown()
    process.exit(1)
  }

  const vite = spawn(
    process.platform === 'win32' ? 'npm.cmd' : 'npm',
    ['run', 'dev', '--', '--host', '0.0.0.0', '--port', String(webPort), '--strictPort'],
    {
      cwd: webDir,
      stdio: 'inherit',
      env: {
        ...process.env,
        VITE_API_PROXY_TARGET: proxyTarget,
      },
    },
  )
  children.push(vite)

  vite.on('exit', (code) => {
    shutdown()
    process.exit(code ?? 0)
  })
}

main().catch((e) => {
  console.error('[dev-stack]', e)
  process.exit(1)
})
