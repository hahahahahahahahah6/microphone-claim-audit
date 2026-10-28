"""Numbered spec cases 1–32; generated exhaustion cases name every template."""
import contextlib
import io
import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch
from microphone_claim_audit.audit import audit, claims, evidence, normalize
from microphone_claim_audit.phrases import MICROPHONE, NOMICROPHONE
from microphone_claim_audit.__main__ import main

ROOT = Path(__file__).resolve().parents[1]
REC = 'import sounddevice\nsounddevice.rec(10)'


class AuditTests(unittest.TestCase):
    def check_case(self, code='', doc=MICROPHONE[0], severity=None, filename='app.py'):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'README.md').write_text(doc)
            if code:
                path = root / filename
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(code)
            result = audit(root)
            self.assertEqual([f['severity'] for f in result['findings']], [severity] if severity else [])
            self.assertEqual(result['verdict'], 'FAIL' if severity == 'HIGH' else 'PASS')
            return result

    def cli(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            try:
                status = main(list(args))
            except SystemExit as exc:
                status = exc.code
        return status, out.getvalue()

    def test_01_plain(self): self.check_case(REC)
    def test_02_alias(self): self.check_case('import sounddevice as sd\nsd.rec(1)')
    def test_03_from_alias(self): self.check_case('from sounddevice import rec as capture\ncapture(1)')
    def test_04_input_stream(self): self.check_case('import sounddevice as sd\nstream=sd.InputStream()\nstream.read(1)')
    def test_05_pyaudio(self): self.check_case('import pyaudio\np=pyaudio.PyAudio()\nstream=p.open()\nstream.read(1)')
    def test_06_pyaudio_chain(self): self.check_case('import pyaudio\np=pyaudio.PyAudio()\np.open().read(1)')
    def test_07_listen(self): self.check_case('from speech_recognition import Recognizer\nr=Recognizer()\nr.listen(source)')
    def test_08_self(self): self.check_case('import speech_recognition as sr\nself.r=sr.Recognizer()\nself.r.record(source)')
    def test_09_chain(self): self.check_case('from speech_recognition import Recognizer\nRecognizer().listen(source)')
    def test_10_import(self):
        self.check_case('import sounddevice', severity='HIGH')
        status, output = self.cli(str(ROOT/'tests/fixtures/bad'), '--json')
        self.assertEqual(status, 2)
        self.assertEqual([f['severity'] for f in json.loads(output)['findings']], ['HIGH'])
    def test_11_string(self): self.check_case('value="microphone"', severity='HIGH')
    def test_12_playback(self): self.check_case('import sounddevice\nfrom playsound import playsound\nsounddevice.play(data)\nplaysound("a.wav")', severity='HIGH')
    def test_13_loading(self): self.check_case('import soundfile, librosa\nsoundfile.read("a.wav")\nlibrosa.load("a.wav")', severity='HIGH')
    def test_14_transcription(self): self.check_case('import whisper\nwhisper.transcribe("a.wav")', severity='HIGH')
    def test_15_microphone_object(self): self.check_case('import speech_recognition as sr\nsr.Microphone()', severity='HIGH')
    def test_16_recognizer_only(self): self.check_case('from speech_recognition import Recognizer\nr=Recognizer()', severity='HIGH')
    def test_17_unbound_listen(self): self.check_case('r.listen(source)', severity='HIGH')
    def test_18_unbound_read(self): self.check_case('stream.read(10)', severity='HIGH')
    def test_19_negative(self):
        result=self.check_case(REC, NOMICROPHONE[14], 'HIGH')
        self.assertEqual(result['findings'][0]['rule'], 'documented-no-microphone-claim-false')
        self.assertEqual(self.cli(str(ROOT/'tests/fixtures/no_microphone'))[0], 2)
    def test_20_no_claim(self): self.check_case(REC, 'Utility')
    def test_21_noun(self): self.check_case('import sounddevice', 'the microphone chapter explains delivery')
    def test_22_user(self):
        for doc in ('speak into your microphone to continue', 'plug in your microphone before starting'):
            self.check_case('import sounddevice', doc)
    def test_23_voice(self): self.check_case('import whisper\nwhisper.transcribe("a.wav")', 'transcribes spoken commands')
    def test_24_no_source(self):
        self.check_case(severity='HIGH')
        self.check_case(doc=NOMICROPHONE[14])
    def test_25_test_only(self):
        self.check_case(REC, severity='MEDIUM', filename='tests/capture.py')
        root=str(ROOT/'tests/fixtures/tests_only')
        self.assertEqual(self.cli(root)[0], 0)
        self.assertEqual(self.cli(root, '--fail-on', 'MEDIUM')[0], 2)
    def test_26_fences(self):
        for marker in ('```', '~~~~'):
            self.check_case(doc=marker+'\n'+MICROPHONE[0]+'\n'+marker)
        self.check_case(doc='`'+MICROPHONE[0]+'`', severity='HIGH')
    def test_27_negation(self):
        self.assertEqual(claims(NOMICROPHONE[0]), (False, True))
        self.assertEqual(claims("doesn't record audio from your microphone"), (False, True))
    def test_28_self_audit(self):
        result=audit(ROOT)
        self.assertEqual(result['verdict'], 'PASS')
        self.assertEqual(result['claims'], {'positive':False, 'negative':False})
        text=normalize((ROOT/'README.md').read_text())
        for phrase in MICROPHONE + NOMICROPHONE:
            self.assertIsNone(re.search(r'\b'+re.escape(phrase)+r'\b', text))
    def test_29_cli(self):
        root=str(ROOT/'tests/fixtures/good')
        self.assertEqual(self.cli('--version'), (0, '0.1.0\n'))
        status, output=self.cli(root, '--json')
        self.assertEqual(status, 0)
        self.assertEqual(json.loads(output)['verdict'], 'PASS')
        self.assertIn('app.py:2', self.cli(root, '--verbose')[1])
        self.assertEqual(self.cli(str(ROOT/'tests/fixtures/bad'), '--ignore', 'README.md')[0], 0)
        self.assertEqual(self.cli('/nonexistent/mca')[0], 1)
        self.assertEqual(self.cli('--unknown')[0], 1)
    def test_30_env_guard(self):
        original=Path.open
        def guarded(path, *args, **kwargs):
            self.assertNotEqual(path.name, '.env')
            return original(path, *args, **kwargs)
        with patch.object(Path, 'open', guarded):
            audit(ROOT)
    def test_31_packaging(self):
        for path in list((ROOT/'microphone_claim_audit').glob('*.py')) + list((ROOT/'tests').glob('*.py')) + [ROOT/'README.md']:
            self.assertIsNone(re.search(r'\b'+'py'+'thon'+r'\b', path.read_text()))
        config=(ROOT/'pyproject.toml').read_text()
        self.assertIn('setuptools>=77', config)
        self.assertIn('license = "MIT"', config)
        self.assertIn('recursive-include tests', (ROOT/'MANIFEST.in').read_text())
    def test_32_phrase_inventory(self):
        self.assertEqual(len(MICROPHONE), 27)
        self.assertEqual(len(NOMICROPHONE), 18)
        self.assertEqual(len(set(MICROPHONE+NOMICROPHONE)),45)

    def test_additional_provider_routes(self):
        for code in (
            'from sounddevice.streams import InputStream as I\nI().read(1)',
            'import sounddevice\nself.s=sounddevice.InputStream()\nself.s.read(1)',
            'from pyaudio import PyAudio as P\nself.p=P()\nself.s=self.p.open()\nself.s.read(1)',
            'import speech_recognition as sr\nsr.Recognizer().record(src)',
            'from speech_recognition.audio import Recognizer as R\nr=R()\nr.record(src)',
        ): self.check_case(code)

    def test_explicit_non_evidence(self):
        for code in (
            'input("speak")',
            'import sounddevice as sd\nsd.query_devices()\nsd.wait()\nsd.sleep(1)',
            'import pyaudio\np=pyaudio.PyAudio()\np.open()',
            'import wave, torchaudio\nwave.open("a.wav", "rb")\ntorchaudio.load("a.wav")',
            'import speech_recognition as sr\nr=sr.Recognizer()\nr.recognize_google(data)',
            'import pyttsx3\npyttsx3.init().say("hello")',
            'from gtts import gTTS\ngTTS("hello").save("a.mp3")',
            'from other import InputStream\ns=InputStream()\ns.read(1)',
            'def record_audio():\n    print("record")\n    return 1',
            '@app.get("/audio")\ndef route():\n    return "audio"',
            'import subprocess\nsubprocess.run(["arecord"])',
            '# sounddevice.rec(1)\n"""sd.rec(1)"""',
            'from other import rec\nrec(1)',
        ): self.check_case(code, severity='HIGH')

    def test_scopes_and_symlinks(self):
        for filename in ('fixtures/a.py','docs/a.py','examples/a.py'):
            self.check_case(REC, severity='HIGH', filename=filename)
        for filename in ('test_capture.py','capture_test.py'):
            self.check_case(REC, severity='MEDIUM', filename=filename)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'README.md').write_text(MICROPHONE[0])
            (root/'link.py').symlink_to(ROOT/'tests/fixtures/good/app.py')
            self.assertEqual(audit(root)['findings'][0]['severity'], 'HIGH')
            (root/'README.md').write_text('Utility')
            (root/'nested/docs').mkdir(parents=True)
            (root/'nested/docs/a.md').write_text(NOMICROPHONE[14])
            (root/'app.py').write_text(REC)
            self.assertEqual(audit(root)['findings'][0]['severity'], 'HIGH')

    def test_normalization_and_family_limit(self):
        self.assertEqual(claims('RECORDS-AUDIO\nFROM YOUR MICROPHONE'), (True,False))
        self.assertEqual(claims('xrecords audio from your microphonex'), (False,False))
        result=self.check_case(doc='\n\n'.join(MICROPHONE), severity='HIGH')
        self.assertEqual(len(result['findings']), 1)
        self.assertEqual(claims(MICROPHONE[0]+'\n\n'+NOMICROPHONE[0]), (True, True))


def positive_case(phrase):
    def test(self):
        self.assertEqual(claims(phrase), (True, False))
        self.check_case(doc=phrase, severity='HIGH')
        self.check_case(REC, phrase)
    return test


def negative_case(phrase):
    def test(self):
        self.assertEqual(claims(phrase), (False, True))
        result=self.check_case(REC, phrase, 'HIGH')
        self.assertEqual(result['findings'][0]['rule'], 'documented-no-microphone-claim-false')
        self.check_case(doc=phrase)
    return test


# Each generated test covers the exact phrase included in its method name.
for family, phrases, factory in (('positive', MICROPHONE, positive_case), ('negative', NOMICROPHONE, negative_case)):
    for phrase in phrases:
        setattr(AuditTests, 'test_32_exhaustion_'+family+'_'+phrase.replace(' ', '_'), factory(phrase))
