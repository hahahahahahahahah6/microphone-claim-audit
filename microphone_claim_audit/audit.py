"""Static analysis; audited source is never imported or executed."""
import ast
import fnmatch
import re
from pathlib import Path
from .phrases import MICROPHONE, NOMICROPHONE


def normalize(text):
    return re.sub(r'\s+', ' ', text.lower().replace("n't", ' not').replace('-', ' ')).strip()


def pattern(phrases):
    return re.compile(r'\b(?:' + '|'.join(re.escape(p) for p in sorted(phrases, key=len, reverse=True)) + r')\b')


def claims(text):
    lines = []
    fence = None
    for line in text.splitlines():
        match = re.match(r'^\s{0,3}(`{3,}|~{3,})', line)
        if match:
            token = match.group(1)
            if fence is None:
                fence = token
            elif token[0] == fence[0] and len(token) >= len(fence):
                fence = None
            lines.append('')
        elif fence is None:
            lines.append(line)
    yes = no = False
    for paragraph in re.split(r'\n\s*\n', '\n'.join(lines)):
        value = normalize(paragraph)
        no = no or bool(pattern(NOMICROPHONE).search(value))
        value = pattern(NOMICROPHONE).sub(' ', value)
        yes = yes or bool(pattern(MICROPHONE).search(value))
    return yes, no


def dotted(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = dotted(node.value)
        return base + '.' + node.attr if base else None
    return None


def evidence(text):
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    aliases = {}
    providers = ('sounddevice', 'pyaudio', 'speech_recognition')
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for item in node.names:
                if item.name.split('.')[0] in providers:
                    aliases[item.asname or item.name.split('.')[0]] = item.name if item.asname else item.name.split('.')[0]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module and node.module.split('.')[0] in providers:
            for item in node.names:
                if item.name != '*':
                    aliases[item.asname or item.name] = node.module + '.' + item.name

    def resolved(node):
        name = dotted(node)
        if not name:
            return ''
        first, *tail = name.split('.')
        return '.'.join([aliases.get(first, ''), *tail]) if first in aliases else ''

    def creation(node, provider, symbol):
        name = resolved(node.func) if isinstance(node, ast.Call) else ''
        return name.startswith(provider + '.') and name.split('.')[-1] == symbol

    bound = {}

    def kind(node):
        if creation(node, 'sounddevice', 'InputStream'):
            return 'input'
        if creation(node, 'pyaudio', 'PyAudio'):
            return 'pa'
        if creation(node, 'speech_recognition', 'Recognizer'):
            return 'recognizer'
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == 'open' and bound.get(dotted(node.func.value)) == 'pa':
            return 'stream'
        return bound.get(dotted(node))

    assignments = [n for n in ast.walk(tree) if isinstance(n, ast.Assign)]
    for _ in range(len(assignments) + 1):
        changed = False
        for node in assignments:
            value = kind(node.value)
            for target in node.targets:
                name = dotted(target)
                if name and (isinstance(target, ast.Name) or name.startswith('self.')) and value and bound.get(name) != value:
                    bound[name] = value
                    changed = True
        if not changed:
            break
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = resolved(node.func)
        hit = name.startswith('sounddevice.') and name.split('.')[-1] == 'rec'
        if isinstance(node.func, ast.Attribute):
            receiver = kind(node.func.value)
            hit = hit or (node.func.attr == 'read' and receiver in ('input', 'stream')) or (node.func.attr in ('listen', 'record') and receiver == 'recognizer')
        if hit:
            found.append(node.lineno)
    return sorted(set(found))


def audit(root, ignores=(), fail_on='HIGH'):
    root = Path(root)
    if not root.is_dir():
        raise ValueError('root must be a readable directory')
    # Explicitly probe listing so unreadable roots produce a usage error.
    list(root.iterdir())
    positive = negative = False
    prod = []
    test = []
    for path in sorted(root.rglob('*')):
        relative = path.relative_to(root)
        parts = relative.parts
        if path.is_symlink() or any((root.joinpath(*parts[:i])).is_symlink() for i in range(1, len(parts))) or not path.is_file():
            continue
        name = relative.as_posix()
        if any(fnmatch.fnmatchcase(name, glob) for glob in ignores):
            continue
        if path.suffix.lower() == '.md' and (name == 'README.md' or 'docs' in parts[:-1]):
            yes, no = claims(path.read_text(encoding='utf-8'))
            positive |= yes
            negative |= no
        if path.suffix != '.py':
            continue
        if any(p in ('fixtures', 'docs', 'examples') for p in parts[:-1]):
            continue
        is_test = 'tests' in parts[:-1] or path.name.startswith('test_') or path.name.endswith('_test.py')
        for line in evidence(path.read_text(encoding='utf-8')):
            (test if is_test else prod).append(f'{name}:{line}')
    findings = []
    if positive and not prod:
        findings.append(dict(rule='documented-microphone-claim-false', severity='MEDIUM' if test else 'HIGH', message='Documented local audio input capture lacks production source evidence.'))
    if negative and prod:
        findings.append(dict(rule='documented-no-microphone-claim-false', severity='HIGH', message='Documented absence conflicts with production source evidence.'))
    failed = any(f['severity'] == 'HIGH' or fail_on == 'MEDIUM' for f in findings)
    return dict(verdict='FAIL' if failed else 'PASS', findings=findings, claims={'positive': positive, 'negative': negative}, evidence=prod, test_evidence=test)
