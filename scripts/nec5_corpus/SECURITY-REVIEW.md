# Security review of nec5_corpus.py version 1.10

Reviewed 2026-09-10 by Claude (Anthropic's model, working in Claude Code) at
the request of the tool's author, Steven Burns, by reading the whole source
of `scripts/nec5_corpus/nec5_corpus.py` and the build that freezes it. This
file ships beside `nec5_corpus.exe` so that a reader can see, before running
it, what the program can and cannot do to their machine. It is a code
review, not a penetration test, and it speaks for **version 1.10 only**: the
test suite refuses a version bump that does not re-state the version here,
so a stale review cannot ship by accident.

**Re-read 2026-09-13 for 1.10** (antennaknobs#1442, #1435). Two changes to
`translate` only. A `GN 2` card is now written as `GN 2` instead of `GN 0`.
When two sources would write the same output file, one is kept and the
other is reported as a `collision` rather than overwriting it. Neither
change adds a file, network or process behaviour, and the second one
writes less. Every claim below stands as written.

## The short version

The program is a 2,000-line Python script that reads antenna decks (text
files), rewrites them, and optionally runs a NEC-5 engine that **you** point
it at. It uses nothing outside Python's standard library. Specifically:

- **Network.** Only the `fetch` subcommand touches the network, and only to
  download from the fixed list of sources printed by `list` (GitHub
  archive zips, the ARRL and Cebik model collections, a few personal sites).
  `translate`, `check` and `compare` make no network connection at all.
  Nothing is uploaded, nothing reports home, no analytics, no update check.
- **Files.** It writes only under the folders you name (`--out`,
  `--report`, `--keep-dir`) and in a temporary folder it creates and removes
  for each engine run. It never writes to your home folder, the registry,
  startup items, PATH, or anywhere it was not told to.
- **Programs.** The only program it starts is the NEC-5 executable you pass
  to `check --exe`, once per deck, with the deck's file name on its
  standard input, in a temporary working folder, with a timeout. It uses no
  shell, so nothing in a deck or a file name is interpreted as a command.
- **Code execution.** There is no `eval`, `exec`, `pickle`, `os.system`,
  dynamic import, or compiled extension. 4nec2 `SY` expressions in decks
  are parsed by a small hand-written arithmetic evaluator, not by Python.
- **Environment.** It reads a fixed list of thread-related environment
  variables (`OMP_NUM_THREADS` and the like) to record in `check` reports. It
  changes none of them in YOUR shell. Since 1.7 it does set three of them —
  `OMP_NUM_THREADS`, `OPENBLAS_NUM_THREADS`, `MKL_NUM_THREADS` — to `1` in the
  environment it hands the engine, and only when `check --jobs` is above 1 and
  only for variables you have not set yourself; the value used is recorded in the
  report. That is a child process's environment, not the machine's, and it exists
  so N concurrent engines do not each ask for every core.

## What each subcommand does

**`list`** prints the source table. No I/O beyond the console.

**`fetch --out raw`** downloads the public NEC-2 deck collections. Each
download is a plain HTTP(S) GET with a `User-Agent` naming this tool and its
version; three retries; 120 s timeout. Zip archives are opened in memory and
only members whose names end in `.nec` or `.inp` are read; a member is kept
only if it looks like a NEC deck (a content check) and is not a byte-for-byte
duplicate. Web pages are scanned for links to deck files with a regular
expression. Everything kept is written as a plain file under
`raw/<source>/`, plus a `LICENSES.md` naming each source's terms. Downloaded
content is **data**: it is written to disk and never executed, imported or
evaluated.

**`translate --src raw --out nec5`** reads every `.nec`/`.inp` under `--src`,
rewrites it into NEC-5's conventions, and writes the result under `--out`
at the same relative path, with a `translate-report.jsonl`. Pure text
processing; no network; no subprocess.

**`check --exe <NEC5CL> --src nec5`** runs each translated deck through the
engine you name. For each deck: a temporary folder is created, the deck is
written there as `model.nec`, the engine is started with that folder as its
working directory and `model.nec\nmodel.out\n\n` on its standard input,
and the printout is read back and classified. The temporary folder is
removed afterwards. `--jobs N` runs N of these at once in threads. With
`--keep-dir`, the printouts of decks that did not solve cleanly are saved
there. The engine is your licensed binary; what it does is up to it, and
this tool neither contains, downloads, nor contacts one.

**`compare a.jsonl b.jsonl`** reads two `check` reports and diffs them. No
writes.

## Findings

1. **Fixed in 1.3: archive path traversal in `fetch`.** Before 1.3, a zip
   member named `../../something.nec` at one of the fetch sources (a
   compromised GitHub repository, a replaced ARRL zip) would have been written
   two folders above `raw/`. The name is the archive's to choose, and
   through 1.2 the sink only stripped a leading slash. 1.3 keeps only the
   plain path components of a member name and additionally checks that the
   resolved destination lies under `raw/<source>/`. Covered by
   `tests/test_nec5_corpus_sink_1376.py`. The only files that could ever have
   been written this way are `.nec`/`.inp` text files that pass the deck
   content check; nothing would have executed them. It was still a hole.

2. **`check` reports contain local paths — mind what you share.** Every
   `check-report.jsonl` opens with a `_meta` row recording, for
   comparability between machines, the interpreter's path (for the frozen
   exe, its own path), the current working directory, the platform string,
   the thread-related environment variables named above, and the size and
   SHA-256 of the engine and every DLL beside it. On Windows those paths
   usually include your user name. Nothing else about your machine is
   recorded, and the report is written locally and sent nowhere; but if you
   post a report, know that it names those paths.

3. **One fetch source is plain `http://`.** The three w8io.com pages in
   the source table are fetched without TLS, so their content could be
   altered in transit by anyone on the path. What arrives is written as text under `raw/` and never
   executed; with finding 1 fixed, the worst outcome is a wrong or junk deck
   file in that folder.

4. **No size limits on downloads.** A fetch source that served a
   multi-gigabyte archive or deck would be read into memory. The sources
   are the fixed public collections, so this is a robustness limit rather
   than an exposure; `fetch` is the only subcommand affected, and you can
   skip it entirely by supplying your own decks to `translate`.

Nothing else of concern was found: no credentials are read or stored, no
persistence is established, no privileged operation is attempted, and the
program exits when its subcommand finishes.

**What 1.4 changed in the script.** Card translation only, and nothing this
review describes: NEC-4's `CW` (catenary wire) is translated instead of
refused, and
its `MX` and `PS` cards are dropped instead of passed through to NEC-5.
`translate` still does pure text processing under the folders you name, with
no network and no subprocess. One adjacent effect, stated so the sentence
above about `fetch` stays exact: the content check that decides whether a
downloaded file looks like a NEC deck now recognises a catenary deck too, so
`fetch` keeps a few files it used to discard — written as text under
`raw/<source>/`, like every other one, and never executed.

**What 1.8 changed, and it touches nothing this review describes.** Arithmetic
inside `translate`, on one function: the two ends of a NEC-2 segment range are
now mapped onto the remeshed wire as range EDGES rather than as segment centres,
so a range that covered a whole wire before the remesh still covers it
afterwards (antennaknobs#1416). It affects the `LD` types that carry a range —
2, 3 and 5 — and `PT`, which is every card the tool remaps by tag and range.

No new input is read, nothing new is written, no program is started, no
environment variable is read or set, and the bundle is the one 1.4 listed. The
change is the value of two integers in a card the tool was already rewriting.

**What 1.9 changed, and it touches nothing this review describes.** One more
refusal reason inside `translate`, decided from the deck text before any engine
runs: two `GW` cards with coincident endpoints are the same wire written twice,
which makes the moment matrix exactly singular, so the deck is classified
`invalid` rather than translated (antennaknobs#1430). Ten public corpus decks
are affected. A `GM` whose tag range names one of the pair and not the other
moves them apart, so such a pair is NOT refused — without that guard three valid
decks would be lost.

No new input is read, nothing new is written, no program is started, no
environment variable is read or set, and the bundle is the one 1.4 listed. The
change reads coordinates the tool was already parsing and returns a different
status.

**What the zip holds.** 1.4 grew the bundle as well, so here is the whole of
it: `nec5_corpus.exe`; `README.txt` (how to run it); `README.md` (the
tool's full documentation); this file; `export_catalog_nec5.py`; and
`catalog-nec5/`, 476 antennaknobs catalog designs written as NEC-5 decks with
a `manifest.json` saying what each one is. The decks and the export script are
MIT and ours to give; they are text, they are input for `check --src
catalog-nec5`, and nothing in the bundle runs them but the NEC-5 engine you
supply. The export happens at BUILD time in a sibling process, which is why
the build environment needs antennaknobs and the exe does not.

**What 1.5 changed.** `translate` alone, and nothing this review describes: it
now REFUSES a deck that is not legal NEC input of any dialect — a
program-control card above `GE`, no `GE` anywhere, or a `GW` with radius 0 and
no `GC` after it — instead of rewriting it and letting the engine reject it.
Refusing is strictly less work than translating: the deck is read, the fault is
named in the report, and no output file is written for it. No new input is
read, nothing new is written, no program is started, and the bundle is the same
one listed above.

**What 1.6 changed.** Reporting, and less than 1.5 even: a deck that is not
valid NEC input now gets its own status in the report (`invalid`, beside
`refused` and `unreadable`) instead of sharing one, and two faults that used to
be filed as "this tool could not read it" — a wire with no segments, an address
no geometry defines — are named as the deck's fault. Every one of those decks
was already being rejected without an output file before this; only the word for
it changed. Nothing new is read, written, or run, and the bundle is the one
listed above.

**What 1.7 changed, and this one DOES touch something the review describes.** For
the first time a release here changes the ENVIRONMENT the engine runs in: with
`check --jobs` above 1, three thread-count variables are set to `1` in the CHILD's
environment unless you set them yourself, so N concurrent engines do not each
claim every core (the measurement is in the README). Your own shell is untouched,
no other variable is read or written, and the report records what was used. The
**Environment** bullet above is corrected accordingly rather than left standing —
it used to say this program modifies none, and that is no longer true.

The rest of 1.7 is reading and refusing, and strictly less of both. `compare` now
reads the row key its own writer writes — through 1.6 it read none, so every
comparison reported "0 decks, 0 moved", a clean pass over nothing — and an empty
comparison exits non-zero. A deck carrying a token that is not a number where NEC
wants one is refused as unreadable instead of being written out with the token
still in it. And `compare` now reads the first impedance row out of each report
beside the status — more of the same file it already opens, nothing new written.
No new input is read, nothing new is written, no program is started, and the
bundle is the one 1.4 listed.

## About the executable

`nec5_corpus.exe` is this script frozen with PyInstaller (one-file mode)
and signed with the antennaknobs / momwire Authenticode certificate. It is
built by a public GitHub Actions workflow
(`.github/workflows/freeze-nec5-corpus.yml` in the repository) from a
commit named in the release notes. The build installs PyInstaller **and**
antennaknobs — the latter only so that a sibling process can write the
catalog decks that ship beside the exe; the exe itself excludes the package
(`--exclude-module antennaknobs`), and the smoke gate runs the unfrozen side
under `python -S`, so a script that had quietly grown a dependency would fail
the lane rather than ship. That gate runs the frozen program and the unfrozen
script over the same 70 decks and requires byte-identical output. The release
notes carry the SHA-256 of the exe and the zip.

What PyInstaller adds is Python itself and a small bootloader: on each
launch the exe unpacks its contents into a temporary folder
(`%TEMP%\_MEIxxxxxx`), runs the script from there, and removes the folder
on exit. That unpacking is also why some antivirus products flag one-file
PyInstaller executables on heuristics alone; the signature and the
checksums are the answer to that, and so is building it yourself.

To verify or rebuild:

- Right-click the exe, Properties, Digital Signatures: the signer is the
  certificate named in the release notes, and the signature is timestamped.
- `certutil -hashfile nec5_corpus.exe SHA256` and compare with the release
  notes.
- Or skip the exe: with any Python 3.8 or newer, download
  `scripts/nec5_corpus/nec5_corpus.py` from the repository and run
  `python nec5_corpus.py ...`. It is the same file, and it needs nothing
  installed.

## Limits of this review

The review covers the script's own code as of version 1.10 and the build
that freezes it. It does not cover Python, PyInstaller, Windows, or the
NEC-5 engine you supply. It was done by reading, with the findings above
confirmed by running the code (finding 1 was reproduced before it was
fixed); no fuzzing or dynamic analysis beyond the test suite was done. A
later version of the script may do more or differently: check that the
version at the top of this file matches `nec5_corpus.exe --version`.
