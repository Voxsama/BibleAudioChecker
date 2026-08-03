# IRV Assamese PDF Validation

Validated source:

- File: `IRVAsm.pdf`
- Pages: 1,952
- SHA-256:
  `0AACAC59DA056DBBF086126295FDEC1E86A78E0ABF87114D1D442F7EE6E148B4`

Parser results:

- 66 canonical books recognized
- 1,189 chapters recognized
- 31,104 numbered verse entries retained
- 0 missing chapter sequences
- WAV matching uses canonical book plus chapter
- Revelation 12 uses the PDF's 18 verses instead of the built-in KJV count

The PDF uses number-first Assamese headings such as `1 অধ্যায়`. Most verse
numbers are inline and followed by a typographic thin space; poetic passages
often use tab-separated verse numbers. Both forms are supported.

Some passages use merged ranges such as `3-4`, `17-18`, or `28-29`. Twelve
secondary verse numbers occur inside such ranges. Because the PDF supplies one
combined text block rather than a separate boundary for each verse, Auto-Mark
interpolates the secondary timestamp at low confidence and requires manual
review.

This validates PDF extraction and book/chapter/verse mapping. It does not
validate Assamese speech timing. A real chapter WAV and a manually checked
reference are still required to measure alignment error.
