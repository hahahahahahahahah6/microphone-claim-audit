# microphone-claim-audit

An offline static audit comparing documentation about local audio input capture
with provider-resolved calls in Python source. Source is parsed, never executed.
There are no runtime dependencies.

Install and run:

```sh
python3 -m pip install .
microphone-claim-audit /path/to/project --json
python3 -m microphone_claim_audit /path/to/project --verbose
python3 -m unittest discover
python3 -m build
```

The positional root must be a readable directory. `--json` emits a JSON object
with verdict, findings, claim flags, and evidence locations. `--verbose` shows
evidence in human output. Repeat `--ignore <glob>` to exclude relative paths.
`--version` prints 0.1.0. `--fail-on HIGH` is the default; `--fail-on MEDIUM`
also fails on evidence confined to tests. Exit status is 0 for PASS, 2 for FAIL,
and 1 for usage or file-access errors. A MEDIUM finding can accompany PASS.

Root README.md and Markdown files beneath any docs path component supply claims.
Fenced blocks are excluded; inline code counts. Matching lowercases, expands
negative contractions, replaces hyphens with spaces, and joins paragraph lines.
Negative spans are removed before positive matching. Each family yields at most
one finding. Positive promises without production evidence are HIGH, or MEDIUM
when only tests contain evidence. Negative promises contradicted by production
calls are HIGH, including promises in docs. No claim yields PASS. Without source,
a positive promise fails and a negative promise passes.

Source analysis resolves imports and aliases for sounddevice, pyaudio, and
speech_recognition. It accepts rec calls, bound InputStream reads, reads from
streams opened by bound PyAudio instances, and bound Recognizer listen/record
calls, including supported self attributes and chained calls. Imports alone,
playback, file loading, transcription, synthesis, and object construction alone
do not establish evidence. Tests are assessed separately. Files beneath fixtures,
docs, and examples, plus symlinked source, are excluded. Environment files are
never opened.

## Limitations

Only the exact templates stored in the package's phrases module are claims.
Bare device nouns, chapter titles, dependency lists, user instructions to speak
or plug in a device, and promises about spoken transcription, synthesis, keys,
screens, clipboard operations, or network delivery are outside this audit.

This is a module-local syntactic check, not a runtime or data-flow proof. It does
not validate hardware, arguments, reachability, callback capture, cross-module
bindings, reassignment, or lexical scope. Invalid syntax supplies no evidence.
Shell audio helpers such as arecord, ffmpeg, and sox are outside the supported
routes. Command names in strings do not establish evidence.

The related voice-claim-audit requires a recognize call paired with a Recognizer.
This audit requires only a capture call: listen without recognize can pass here
and fail there, because the tools judge different promises.
