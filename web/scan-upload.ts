// Dev-server plugin: a phone on the same Wi-Fi sends a room scan (.glb) to this computer.
//   POST /scan-upload?name=<file name>&t=<token>   body = the file      -> {id, name, bytes}
//   GET  /scan-upload/latest                                            -> the newest upload, or {}
//   GET  /scan-upload/file/<id>                                         -> the .glb
// Files land in <repo>/.cache/uploads (gitignored), so the agent server can read the same scan by path.
import { randomBytes } from 'node:crypto'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import type { Plugin } from 'vite'

const MAX_BYTES = 120 * 1024 * 1024

/** This computer's address on the local network, e.g. 192.168.1.23. */
export function lanAddress(): string | null {
  for (const list of Object.values(os.networkInterfaces())) {
    for (const n of list ?? []) {
      if (n.family === 'IPv4' && !n.internal && !n.address.startsWith('169.254.')) return n.address
    }
  }
  return null
}

interface Upload {
  id: string
  name: string
  bytes: number
  at: number
  /** absolute path on this computer, for the agent server's scan_path */
  path: string
}

export function scanUpload(repoRoot: string, port: number): Plugin {
  const dir = path.join(repoRoot, '.cache', 'uploads')
  const token = randomBytes(6).toString('hex')
  const ip = lanAddress()
  let latest: Upload | null = null
  const byId = new Map<string, Upload>()

  return {
    name: 'scan-upload',
    config: () => ({
      define: {
        __LAN_ORIGIN__: JSON.stringify(ip ? `http://${ip}:${port}` : null),
        __UPLOAD_TOKEN__: JSON.stringify(token),
      },
    }),
    configureServer(server) {
      fs.mkdirSync(dir, { recursive: true })
      server.middlewares.use('/scan-upload', (req, res) => {
        const url = new URL(req.url ?? '/', 'http://x')
        const json = (code: number, body: unknown) => {
          res.statusCode = code
          res.setHeader('content-type', 'application/json')
          res.end(JSON.stringify(body))
        }

        if (req.method === 'GET' && url.pathname === '/latest') {
          if (!latest) return json(200, {})
          const local = ['127.0.0.1', '::1', '::ffff:127.0.0.1'].includes(req.socket.remoteAddress ?? '')
          const { path: onDisk, ...rest } = latest
          return json(200, local ? { ...rest, path: onDisk } : rest)
        }

        if (req.method === 'GET' && url.pathname.startsWith('/file/')) {
          const hit = byId.get(url.pathname.slice('/file/'.length))
          if (!hit || !fs.existsSync(hit.path)) return json(404, { error: 'no such scan' })
          res.setHeader('content-type', 'model/gltf-binary')
          res.setHeader('content-length', String(hit.bytes))
          fs.createReadStream(hit.path).pipe(res)
          return
        }

        if (req.method === 'POST' && (url.pathname === '/' || url.pathname === '')) {
          if (url.searchParams.get('t') !== token) return json(403, { error: 'This link is out of date. Scan the QR code again.' })
          const name = (url.searchParams.get('name') ?? 'room.glb').replace(/[^\w.\- ]+/g, '_').slice(0, 80)
          if (!/\.glb$/i.test(name)) return json(400, { error: 'Send a .glb file (Polycam: Export, GLB).' })
          const id = `${Date.now().toString(36)}-${randomBytes(3).toString('hex')}`
          const file = path.join(dir, `${id}.glb`)
          const out = fs.createWriteStream(file)
          let bytes = 0
          let failed = false
          req.on('data', (chunk: Buffer) => {
            bytes += chunk.length
            if (bytes > MAX_BYTES && !failed) {
              failed = true
              req.destroy()
              out.destroy()
              fs.unlink(file, () => {})
              json(413, { error: 'That scan is larger than 120 MB.' })
            }
          })
          req.pipe(out)
          out.on('finish', () => {
            if (failed) return
            // A .glb starts with the four bytes "glTF".
            const head = Buffer.alloc(4)
            const fd = fs.openSync(file, 'r')
            fs.readSync(fd, head, 0, 4, 0)
            fs.closeSync(fd)
            if (head.toString('latin1') !== 'glTF') {
              fs.unlink(file, () => {})
              return json(400, { error: 'That file is not a .glb scan.' })
            }
            latest = { id, name, bytes, at: Date.now(), path: file }
            byId.set(id, latest)
            json(200, { id, name, bytes })
          })
          out.on('error', () => !failed && json(500, { error: 'Could not save the scan on the computer.' }))
          return
        }
        json(404, { error: 'not found' })
      })
    },
  }
}
