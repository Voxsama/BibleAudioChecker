# Assamese Auto-Marker: Operator Guide

## Recommended preparation

1. Use one WAV file per chapter.
2. Put the chapter number in the filename, for example `Gen_001.wav`.
3. Load the Bible PDF before starting Auto-Mark.
4. In Settings -> Script STT, use:
   - Language: `Assamese (as)`
   - Assamese precision pack: `Meta MMS Assamese Precision`
5. Click **Auto-Mark Loaded Chapters**.

The bottom progress bar reports the current chapter and processing stage.
When script alignment has determined the marker positions, the app switches
once to **Markers & Waveform** and shows a live preview while the marked WAV
and CSV are being written. It does not display guessed moving markers during
speech analysis; only positions actually produced by the alignment
engine are previewed.

If the model is not installed, open **Processing -> AI Model Packs**, select
`Meta MMS Assamese Precision`, and click **Download / Verify**. The application
downloads approximately 3.60 GiB and checksum-verifies every pinned file;
packaged end users do not need Python or a terminal. This pack is licensed
CC-BY-NC 4.0 and is for non-commercial use.

The app matches the chapter number in each WAV filename to the same chapter
number extracted from the PDF. It creates:

- `filename_marked.wav`
- `filename_marked.csv`

The original WAV is not overwritten.

For another language, select it from the same language dropdown before
starting Auto-Mark. The choice is saved in the app settings. Use Auto-detect
only when the recording language is genuinely unknown; explicitly selecting
the language is normally more reliable.

For this IRV Assamese recording set, do not use automatic language detection:
Whisper can confidently classify Assamese as Bengali. Force `Assamese (as)`.
The app's detection report now uses distinctive Assamese letters in the
matching loaded PDF chapter to show **Assamese — PDF script confirmed**, while
still displaying Bengali as Whisper's raw acoustic guess for transparency.
Assamese Auto-Mark automatically prefers Meta MMS's native `asm` CTC adapter.
It aligns frame-derived Assamese words monotonically against the exact PDF,
then refines starts using nearby pauses. Whisper's Bengali acoustic decoder is
retained only as a fallback when the MMS pack is unavailable. This does not
change the project language or PDF: alignment and reporting remain Assamese.
The expensive word timeline is cached per audio file/model and reused until
the audio changes.

Transcript anchors are accepted only when at least 8% of the chapter script
matches. Lower overlap is rejected instead of clustering interpolated verses;
the app creates a chronological pause-based draft and requires review.

If you do not know the language, add representative chapter audio and click
**Detect Languages** in Processing. The result shows the top three candidates
and confidence. When all confident files agree, the app offers to use that
language for the project. Ambiguous results stay in the Review Queue instead
of being silently trusted.

## Reviewing the result

Open **Markers & Waveform**, select the generated marked file, and check:

- Chapter Title appears before Verse 1.
- Optional Heading markers agree with the bold section headings extracted from
  the PDF.
- Every expected marker from Verse 1 through the last verse is present.
- Each marker is at the required speech boundary.
- Results marked **DRAFT** are reviewed before delivery.

Auto-Mark is deliberately conservative. A complete marker count does not mean
that every timestamp is final. Low-confidence or interpolated timestamps are
shown as drafts.

You can drag a marker on the waveform, edit its exact time or label, snap it to
nearby speech or a zero crossing, undo/redo, preview around it, and save a new
reviewed WAV. Accepted corrections are stored by language and optional
reader/narrator profile.

## PDF formats currently recognized

Chapter headings should be on their own line and look like one of these:

- `Chapter 1`
- Assamese `অধ্যায় ১`
- Assamese `অধ্যায় ১`
- IRV Assamese `1 অধ্যায়`

Verse numbers may use Western digits or Assamese/Bengali digits. PDF text
extraction can change the reading order, so the exact production PDF must be
tested.

The supplied `IRVAsm.pdf` is recognized as a complete 66-book Bible. Its 1,189
chapters are matched by both canonical book and chapter from WAV filenames, so
chapters with the same number in different books do not overwrite one another.
It contains 31,104 numbered verse entries. Revelation 12 has verse 18 in this
translation, so the loaded script's verse numbering overrides the built-in KJV
count for QC and Auto-Mark.

The PDF's bold typography also yields 2,097 section-heading records. Enable
**Auto-create Heading markers from PDF section headings** in Settings ->
Markers to include them.

Twelve verse entries belong to printed ranges such as `3-4`. The PDF contains
one combined text block for each such range, not two independent boundaries.
The app keeps both verse numbers but deliberately gives the second boundary a
low-confidence interpolated timestamp that must be reviewed.

## Two-second silence controls

Open **Settings -> Mastering** and select either or both:

- Fix FRONT silence
- Fix BACK silence

Then use **Apply Silence Settings** for silence-only processing, or
**Master Loaded Chapters** for the full mastering chain. Front trimming or
padding shifts embedded marker samples by the exact same amount. Back-only
processing does not move markers.

## Calibration needed for production accuracy

Before treating Assamese Auto-Mark as production-ready, benchmark it with one
real chapter:

- the exact Bible PDF;
- the raw Assamese chapter WAV;
- a manually checked marker CSV or marked reference WAV, if available;
- the marker convention: first spoken syllable, or the start/end of the pause
  before the verse.

Use the **Calibration** tab to compare automatic WAV/CSV/JSON markers against
the reference and measure median, 95th percentile, worst-case error, and pass
rate. Export CSV/JSON evidence for each trial. Those results determine whether the
current MMS CTC alignment is sufficient or whether narrator-specific
fine-tuning is needed.
