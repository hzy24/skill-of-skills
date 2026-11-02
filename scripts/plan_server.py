#!/usr/bin/env python3
"""Serve one plan's editor storage on loopback. Python 3.9+ on macOS/Linux, standard library only.

Run through the host's background Bash tool. The HTML remains the delivered
file; this process supplies its save/read channel and never executes the plan.
"""
import argparse
import fcntl
import copy
import hmac
import json
import os
from pathlib import Path
import secrets
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

import sos
from plan_io import edit_lock
from plan_status import assess


MAX_BODY = 2 * 1024 * 1024
TOKEN_HEADER = 'X-Skill-Of-Skills-Token'
DEFAULT_ORIGIN = 'http://127.0.0.1:17860'


class PlanConflict(ValueError):
    pass


def atomic_write(path, content):
    """Publish a complete, private file without a predictable temporary name."""
    path = Path(path)
    fd, temporary = tempfile.mkstemp(prefix='.' + path.name + '-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def json_script(value):
    return (json.dumps(value, ensure_ascii=False)
            .replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026'))


def allowed_origin(value):
    parsed = urlsplit(value)
    if (parsed.scheme not in ('http', 'https') or not parsed.netloc or
            parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment):
        raise ValueError('Origin 须为完整的 http(s) 来源，不含路径、查询或凭据')
    # Reject malformed ports as well as stray URL syntax before using as a header.
    _ = parsed.port
    if any(c.isspace() for c in value):
        raise ValueError('Origin 不能包含空白')
    return value


class PlanStore:
    def __init__(self, plan_path, html_path, meta_path):
        raw_plan = Path(plan_path)
        if not raw_plan.is_absolute():
            raise ValueError('--plan 需要绝对路径')
        self.plan_path = raw_plan.resolve(strict=True)
        self.root = self.plan_path.parent
        self.html_path = self._output_path(html_path)
        self.meta_path = self._output_path(meta_path)
        if len({self.plan_path, self.html_path, self.meta_path}) != 3:
            raise ValueError('plan、html 和 meta 路径需要各不相同')
        self.lock = threading.Lock()
        self.token = secrets.token_urlsafe(32)
        self.endpoint = None
        sos.require_plan(sos.read(self.plan_path))

    def _output_path(self, path):
        candidate = Path(path).resolve()
        if not candidate.is_relative_to(self.root):
            raise ValueError('HTML 和状态文件须保存在 plan.json 所在工作目录内')
        if not candidate.parent.is_dir():
            raise ValueError('输出文件的父目录需要存在')
        if candidate.exists() and not candidate.is_file():
            raise ValueError('输出路径须为文件')
        return candidate

    def read(self):
        plan = sos.read(self.plan_path)
        sos.require_plan(plan)
        return {'plan': plan, 'hash': sos.digest(plan), 'readiness': assess(plan)}

    def render_html(self, plan):
        template = Path(__file__).resolve().parents[1] / 'assets' / 'plan.html'
        html = template.read_text(encoding='utf-8')
        html = html.replace('__PLAN_DATA__', json_script(plan)).replace('__PLAN_HASH__', sos.digest(plan))
        config = json_script({'endpoint': self.endpoint, 'token': self.token})
        bridge = '''<script>
(() => {
  const config = CONFIG;
  async function call(method, request) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 10000);
    try {
      const response = await fetch(config.endpoint, {
        method, mode: 'cors', credentials: 'omit', cache: 'no-store',
        headers: {'X-Skill-Of-Skills-Token': config.token,
          ...(method === 'POST' ? {'Content-Type': 'application/json'} : {})},
        ...(method === 'POST' ? {body: JSON.stringify(request)} : {}),
        signal: controller.signal
      });
      const result = await response.json();
      if (!response.ok || (method === 'POST' && result.persisted !== true)) {
        const error = new Error(result.error || '方案保存失败');
        error.status = response.status;
        throw error;
      }
      return result;
    } finally { clearTimeout(timer); }
  }
  window.skillOfSkillsStorage = Object.freeze({
    save: request => call('POST', request), load: () => call('GET')
  });
})();
</script>
'''.replace('CONFIG', config)
        # Insert before any editor scripts; these detect the storage at startup.
        if '<script' in html:
            html = html.replace('<script', bridge + '<script', 1)
        elif '</head>' in html:
            html = html.replace('</head>', bridge + '</head>', 1)
        else:
            html = bridge + html
        return html

    def publish(self, endpoint, origins):
        self.endpoint = endpoint
        snapshot = self.read()
        atomic_write(self.html_path, self.render_html(snapshot['plan']))
        meta = {'version': 1, 'pid': os.getpid(), 'endpoint': endpoint,
                'plan': str(self.plan_path), 'html': str(self.html_path),
                'origins': sorted(origins), 'token': self.token}
        atomic_write(self.meta_path, json.dumps(meta, ensure_ascii=False, indent=2))

    def update(self, request):
        if not isinstance(request, dict) or request.get('action') != 'update_plan':
            raise ValueError('保存接口只接受 update_plan；执行请在对话中确认')
        allowed = {'action', 'plan_id', 'base_revision', 'base_hash', 'changes', 'remove_nodes'}
        if set(request) - allowed:
            raise ValueError('修改请求包含未知字段')
        request = copy.deepcopy(request)
        removed = request.pop('remove_nodes', [])
        if (not isinstance(removed, list) or any(not isinstance(v, str) for v in removed)
                or len(set(removed)) != len(removed)):
            raise ValueError('删除模块需要无重复的标识列表')
        changes = request.setdefault('changes', {})
        if not isinstance(changes, dict):
            raise ValueError('changes 须为对象')
        nodes = changes.setdefault('nodes', [])
        if not isinstance(nodes, list):
            raise ValueError('模块修改须为列表')
        nodes[:]=[edit for edit in nodes if not isinstance(edit,dict) or edit.get('id') not in removed]
        nodes.extend({'id': nid, 'remove': True} for nid in removed)
        with self.lock, edit_lock(self.plan_path):
            current = self.read()['plan']
            if (request.get('plan_id') != current['id'] or
                    request.get('base_revision') != current['revision'] or
                    request.get('base_hash') != sos.digest(current)):
                raise PlanConflict('保存失败：方案已有新版本。请保留当前草稿，读取最新方案后再合并修改。')
            updated = sos.apply_edits(current, request)
            # Validation includes graph, deliverable and content-outline references.
            # Explicit cancellation records removed requirements and preserves shared scope.
            atomic_write(self.plan_path, json.dumps(updated, ensure_ascii=False, indent=2))
            saved = self.read()
            if saved['hash'] != sos.digest(updated):
                raise PlanConflict('保存后的方案发生变化，请重新读取最新方案')
            refreshed = True
            try:
                atomic_write(self.html_path, self.render_html(saved['plan']))
            except OSError:
                # The canonical JSON is already committed; never mislabel this as
                # an unsaved edit and provoke a duplicate write with an old hash.
                refreshed = False
            return {'persisted': True, **saved, 'html_refreshed': refreshed}


class PlanServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, store, origins=None):
        self.store = store
        self.origins = {allowed_origin(v) for v in (origins or [DEFAULT_ORIGIN])}
        # Lock a stable sidecar, not the atomically replaced plan inode.
        self.lease = open(str(store.plan_path)+'.lock','a')
        try:
            fcntl.flock(self.lease.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.lease.close()
            raise ValueError('同一 plan.json 已有保存服务；复用现有服务或先停止旧进程')
        try:
            super().__init__(('127.0.0.1', 0), PlanHandler)
        except BaseException:
            self.lease.close()
            raise
        self.origin = 'http://127.0.0.1:' + str(self.server_address[1])
        self.origins.add(self.origin)
        self.expected_host = urlsplit(self.origin).netloc
        try:
            self.store.publish(self.origin + '/plan', self.origins)
        except BaseException:
            self.server_close()
            raise

    def server_close(self):
        try:super().server_close()
        finally:
            if hasattr(self,'lease') and not self.lease.closed:self.lease.close()


class PlanHandler(BaseHTTPRequestHandler):
    server_version = 'SkillPlan/1'

    def log_message(self, *_args):
        pass  # Never log capabilities, request bodies or business contents.

    def respond(self, status, value):
        body = json.dumps(value, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        origin = self.headers.get('Origin')
        if origin in self.server.origins:
            self.send_header('Access-Control-Allow-Origin', origin)
            self.send_header('Vary', 'Origin')
            if self.command == 'OPTIONS':
                self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
                self.send_header('Access-Control-Allow-Headers', TOKEN_HEADER + ', Content-Type')
                if self.headers.get('Access-Control-Request-Private-Network') == 'true':
                    self.send_header('Access-Control-Allow-Private-Network', 'true')
        self.end_headers()
        self.wfile.write(body)

    def context_ok(self):
        if self.headers.get('Host') != self.server.expected_host:
            self.respond(403, {'error': 'Host 不受支持'}); return False
        origin = self.headers.get('Origin')
        if origin is not None and origin not in self.server.origins:
            self.respond(403, {'error': '页面来源未获允许'}); return False
        return True

    def authorized(self):
        supplied = self.headers.get(TOKEN_HEADER, '')
        if not hmac.compare_digest(supplied.encode('utf-8'), self.server.store.token.encode('utf-8')):
            self.respond(401, {'error': '保存连接未获授权，请重新打开当前任务方案'}); return False
        return True

    def do_OPTIONS(self):
        if not self.context_ok(): return
        if self.path not in ('/health', '/plan'):
            self.respond(404, {'error': '未知路径'}); return
        requested = {h.strip().lower() for h in self.headers.get('Access-Control-Request-Headers', '').split(',') if h.strip()}
        if (self.headers.get('Origin') not in self.server.origins or
                self.headers.get('Access-Control-Request-Method') not in ('GET', 'POST') or
                requested - {TOKEN_HEADER.lower(), 'content-type'}):
            self.respond(403, {'error': '预检请求未获允许'}); return
        self.respond(200, {'ready': True})

    def do_GET(self):
        if not self.context_ok(): return
        if self.path == '/health':
            self.respond(200, {'ready': True}); return
        if self.path != '/plan':
            self.respond(404, {'error': '未知路径'}); return
        if not self.authorized(): return
        try:
            with self.server.store.lock:
                snapshot = self.server.store.read()
            self.respond(200, snapshot)
        except (OSError, ValueError, TypeError, KeyError):
            self.respond(422, {'error': '当前方案文件无法读取或校验，请由 Agent 修复后重试'})

    def do_POST(self):
        if not self.context_ok(): return
        if self.path != '/plan':
            self.respond(404, {'error': '未知路径'}); return
        if not self.authorized(): return
        if self.headers.get('Content-Type', '').split(';')[0].strip().lower() != 'application/json':
            self.respond(415, {'error': '保存请求需要 application/json'}); return
        try:
            length = int(self.headers.get('Content-Length', '0'))
        except ValueError:
            length = 0
        if not 0 < length <= MAX_BODY or self.headers.get('Transfer-Encoding'):
            self.respond(413, {'error': '请求大小无效或超出限制'}); return
        self.connection.settimeout(10)
        try:
            data = self.rfile.read(length)
            if len(data) != length: raise ValueError('请求内容不完整')
            request = json.loads(data.decode('utf-8'))
            self.respond(200, self.server.store.update(request))
        except PlanConflict as exc:
            self.respond(409, {'error': str(exc)})
        except (ValueError, KeyError, TypeError) as exc:
            self.respond(422, {'error': '保存失败：' + str(exc)})
        except (OSError, TimeoutError):
            self.respond(503, {'error': '保存服务暂时不可用，请保留草稿并重试'})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', required=True, help='Absolute canonical plan.json path')
    parser.add_argument('--html', required=True, help='Delivered HTML file in the plan directory')
    parser.add_argument('--meta', required=True, help='Private service state file in the plan directory')
    parser.add_argument('--origin', action='append', help='Allowed browser origin; repeat for additional origins')
    args = parser.parse_args()
    store = PlanStore(args.plan, args.html, args.meta)
    with PlanServer(store, args.origin) as server:
        print(json.dumps({'ready': True, 'endpoint': server.origin, 'html': str(store.html_path),
                          'meta': str(store.meta_path)}, ensure_ascii=False), flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == '__main__':
    main()
