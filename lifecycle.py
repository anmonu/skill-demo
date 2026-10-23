"""Deterministic demo policy and lifecycle. Never executes submitted instructions."""
import hashlib
import io
import json
import re
import sqlite3
import zipfile
from datetime import datetime, timezone

STAGES = ['draft', 'submitted', 'scanned', 'built', 'approved', 'published', 'revoked']
ACTORS = {'employee': ('alex', 'Employee'), 'reviewer': ('sam', 'Security reviewer'), 'admin': ('jordan', 'Organisation admin')}

class PolicyError(ValueError):
    pass


def scan(manifest):
    """Small illustrative deny-list; not a comprehensive security scanner."""
    findings = []
    text = manifest.get('instructions', '')
    checks = [
        ('secret', r'(?i)(?:api[_-]?key|password|token)\s*[:=]\s*[\w-]{8,}', 'Possible embedded credential'),
        ('destructive', r'(?i)\brm\s+-[a-z]*r[a-z]*f\b|\brm\s+-[a-z]*f[a-z]*r\b', 'Destructive shell instruction'),
        ('injection', r'(?i)ignore\s+(?:all\s+)?(?:previous|prior)\s+instructions', 'Instruction override pattern'),
        ('remote-exec', r'(?i)curl\b[^\n]*\|\s*(?:ba)?sh\b', 'Remote shell execution pattern'),
    ]
    for code, pattern, message in checks:
        if re.search(pattern, text):
            findings.append({'code': code, 'severity': 'high', 'message': message})
    if manifest.get('permissions') != ['read:provided-input']:
        findings.append({'code': 'permissions', 'severity': 'high', 'message': 'Demo policy permits only read:provided-input'})
    if re.search(r'https?://', text):
        findings.append({'code': 'network', 'severity': 'high', 'message': 'External URLs require a production network review'})
    return {'passed': not findings, 'findings': findings, 'checks': ['Credential patterns', 'Unsafe instructions', 'Permission allowlist', 'External URLs'], 'scanner': 'demo-policy-v1'}


def validate(data):
    required = ['name', 'version', 'description', 'instructions', 'scope', 'permissions']
    if not isinstance(data, dict) or any(key not in data for key in required):
        raise PolicyError('Complete every required manifest field.')
    if not isinstance(data['name'], str) or not re.fullmatch(r'[a-z][a-z0-9-]{2,49}', data['name']):
        raise PolicyError('Name must be 3–50 lowercase letters, numbers or hyphens, starting with a letter.')
    if not isinstance(data['version'], str) or not re.fullmatch(r'\d+\.\d+\.\d+', data['version']):
        raise PolicyError('Version must use major.minor.patch, for example 1.0.0.')
    for field, limit in [('description', 300), ('instructions', 10000)]:
        if not isinstance(data[field], str) or not data[field].strip() or len(data[field]) > limit:
            raise PolicyError(f'{field} must contain 1–{limit} characters.')
    if data['scope'] not in ['individual', 'organisation']:
        raise PolicyError('Choose individual or organisation scope.')
    if not isinstance(data['permissions'], list) or any(not isinstance(p, str) for p in data['permissions']):
        raise PolicyError('Permissions must be a list of strings.')
    return {key: data[key] for key in required}


def package(manifest):
    target = io.BytesIO()
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as archive:
        for path, content in [('manifest.json', json.dumps(manifest, sort_keys=True, indent=2)), ('SKILL.md', '# ' + manifest['name'] + '\n\n' + manifest['instructions'] + '\n')]:
            info = zipfile.ZipInfo(path, (2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, content)
    return target.getvalue()


class Store:
    def __init__(self, path):
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''
          CREATE TABLE IF NOT EXISTS skills (
            id INTEGER PRIMARY KEY, manifest TEXT NOT NULL, owner TEXT NOT NULL,
            status TEXT NOT NULL, report TEXT, artifact BLOB, digest TEXT, approved_by TEXT,
            UNIQUE(manifest)
          );
          CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY, skill_id INTEGER NOT NULL, actor TEXT NOT NULL,
            action TEXT NOT NULL, detail TEXT NOT NULL, created TEXT NOT NULL
          );
        ''')
        self.db.commit()

    def event(self, sid, actor, action, detail):
        self.db.execute('INSERT INTO events(skill_id, actor, action, detail, created) VALUES(?,?,?,?,?)', (sid, actor, action, detail, datetime.now(timezone.utc).isoformat()))

    def list(self):
        rows = self.db.execute('SELECT * FROM skills ORDER BY id DESC').fetchall()
        return [self.public(row) for row in rows]

    def public(self, row):
        return {'id': row['id'], **json.loads(row['manifest']), 'owner': row['owner'], 'status': row['status'], 'report': json.loads(row['report']) if row['report'] else None, 'digest': row['digest'], 'approved_by': row['approved_by']}

    def audit(self):
        return [dict(row) for row in self.db.execute('SELECT * FROM events ORDER BY id DESC')]

    def create(self, data, role):
        if role != 'employee':
            raise PolicyError('Create skills as the employee.')
        manifest = validate(data)
        with self.db:
            for row in self.db.execute('SELECT manifest FROM skills'):
                existing = json.loads(row['manifest'])
                if existing['name'] == manifest['name'] and existing['version'] == manifest['version']:
                    raise PolicyError('That name and version already exist. Increment the version.')
            cursor = self.db.execute('INSERT INTO skills(manifest,owner,status) VALUES(?,?,?)', (json.dumps(manifest, sort_keys=True), ACTORS[role][0], 'draft'))
            sid = cursor.lastrowid
            self.event(sid, ACTORS[role][0], 'created', manifest['name'] + '@' + manifest['version'])
        return sid

    def action(self, sid, action, role):
        if role not in ACTORS:
            raise PolicyError('Unknown demo role.')
        row = self.db.execute('SELECT * FROM skills WHERE id=?', (sid,)).fetchone()
        if not row:
            raise PolicyError('Skill does not exist.')
        manifest = json.loads(row['manifest'])
        actor = ACTORS[role][0]
        status = row['status']
        with self.db:
            if action == 'submit':
                if role != 'employee' or actor != row['owner'] or status not in ['draft', 'rejected', 'blocked']:
                    raise PolicyError('Only the author can submit a draft or retry a blocked/rejected skill.')
                self.db.execute("UPDATE skills SET status='submitted', report=NULL, artifact=NULL, digest=NULL, approved_by=NULL WHERE id=?", (sid,))
                detail = 'Immutable manifest submitted for checks'
            elif action == 'scan':
                if status != 'submitted':
                    raise PolicyError('Submit the skill before scanning.')
                report = scan(manifest)
                self.db.execute('UPDATE skills SET status=?, report=? WHERE id=?', ('scanned' if report['passed'] else 'blocked', json.dumps(report), sid))
                detail = 'All demo policy checks passed' if report['passed'] else f"Blocked by {len(report['findings'])} finding(s)"
            elif action == 'build':
                if status != 'scanned' or not json.loads(row['report'])['passed']:
                    raise PolicyError('A passing scan is required before building.')
                artifact = package(manifest)
                digest = hashlib.sha256(artifact).hexdigest()
                self.db.execute("UPDATE skills SET status='built', artifact=?, digest=? WHERE id=?", (artifact, digest, sid))
                detail = 'ZIP built; SHA-256 ' + digest
            elif action in ['approve', 'reject']:
                expected = 'admin' if manifest['scope'] == 'organisation' else 'reviewer'
                if role != expected or actor == row['owner'] or status != 'built':
                    raise PolicyError(f'A built skill requires an independent {expected} decision.')
                if not row['artifact'] or hashlib.sha256(row['artifact']).hexdigest() != row['digest']:
                    raise PolicyError('Artifact integrity check failed.')
                self.db.execute('UPDATE skills SET status=?, approved_by=? WHERE id=?', ('approved' if action == 'approve' else 'rejected', actor if action == 'approve' else None, sid))
                detail = f"{manifest['scope'].capitalize()} scope decision bound to SHA-256 {row['digest']}"
            elif action == 'publish':
                expected = 'admin' if manifest['scope'] == 'organisation' else 'reviewer'
                if role != expected or status != 'approved' or not row['approved_by']:
                    raise PolicyError('Publish requires approval and the appropriate reviewer role.')
                if hashlib.sha256(row['artifact']).hexdigest() != row['digest']:
                    raise PolicyError('Artifact integrity check failed.')
                self.db.execute("UPDATE skills SET status='published' WHERE id=?", (sid,))
                detail = f"Published to the demo {manifest['scope']} catalog"
            elif action == 'revoke':
                if role != 'admin' or status != 'published':
                    raise PolicyError('Only an organisation admin can revoke a published skill.')
                self.db.execute("UPDATE skills SET status='revoked' WHERE id=?", (sid,))
                detail = 'Removed from catalog; future downloads disabled'
            else:
                raise PolicyError('Unknown lifecycle action.')
            self.event(sid, actor, action, detail)
        return self.public(self.db.execute('SELECT * FROM skills WHERE id=?', (sid,)).fetchone())

    def download(self, sid, role):
        row = self.db.execute('SELECT * FROM skills WHERE id=?', (sid,)).fetchone()
        if not row or row['status'] != 'published':
            raise PolicyError('Only published artifacts are available.')
        manifest = json.loads(row['manifest'])
        if manifest['scope'] == 'individual' and ACTORS[role][0] != row['owner']:
            raise PolicyError('Individual skills can only be downloaded by their author.')
        if hashlib.sha256(row['artifact']).hexdigest() != row['digest']:
            raise PolicyError('Artifact integrity check failed.')
        with self.db:
            self.event(sid, ACTORS[role][0], 'download', row['digest'])
        return row['artifact'], manifest['name'] + '-' + manifest['version'] + '.zip'
