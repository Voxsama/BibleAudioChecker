# AI Chapter Review — beginner guide

This optional feature uses OpenRouter to explain your local QC results and suggest
possible script/transcript differences. It does **not** prove that a recording or
marker is correct. Automatic verse marking is still disabled.

## 1. Open the review window

1. Open ScriptureSound QC and click **Add Files** to choose a WAV.
2. If you have the matching Bible PDF, click **Load Bible PDF**.
3. In **Chapters & QC**, click the WAV you want to review.
4. Open **Processing → AI Review Chapter…**.

Review one chapter at a time. The app matches PDF text using both the book and
chapter from the filename. `1CH_001.wav` means 1 Chronicles chapter 1, regardless
of where Genesis appears in the PDF or file list. If there is no exact match,
paste the correct chapter instead of assuming a match by chapter number.

## 2. Connect OpenRouter

1. Create/sign in to your account at [OpenRouter](https://openrouter.ai/).
2. Open its **API Keys** page, create a key, and copy it.
3. In the review window's **Connection** tab, paste it into **API key**.
4. Leave **Free models only** checked and use `openrouter/free` initially.
5. Click **Test Connection**. “Key accepted” confirms authentication only.
6. Optionally click **Refresh Free Models** to choose a specific free model.
7. Choose the language you want explanations in, such as English or Hindi.
8. Click **Save Preferences**. This saves the model/options, **not your key**.

Enter the key again after closing the app. Do not put it in GitHub, a screenshot,
project, installer, or message to another person. Each user supplies their own key.

Free-only requests have zero-price provider limits and no paid-model fallback.
Free model availability and rate limits can change. Do not promise unlimited free
reviews to end users. Turning free-only off requires confirmation before a request
that may cost money. A fixed model may give more repeatable results than the free
router, which can choose a different model each time.

## 3. Prepare the chapter on your computer

1. Open the **Chapter** tab.
2. Check the selected book/chapter, translation, extracted text and headings.
   Remove headings only if they are not spoken in this recording. Correct PDF
   extraction errors here. Edits here do not change your PDF.
3. Either paste an **actual transcript** or tick **Generate an independent
   transcript locally**. Do not paste the expected script as the transcript:
   comparing a script with itself cannot verify a recording.
4. Click **Prepare Locally & Preview**. Wait while local measurements and any
   requested transcription finish. The progress indicator shows that work is in
   progress; it is not an invented completion percentage.

Local transcription needs a previously installed model, chosen in
**Settings → Script STT** / **Processing → AI Model Packs**. Assamese uses the Meta
MMS Assamese pack. Other supported languages use local Whisper. Unsupported
languages are not silently replaced. This review feature never uses the existing
cloud transcription setting or downloads a model automatically. If local speech
recognition is unavailable, paste a transcript or review local QC alone.

Measurements, silence checks and marker reading happen locally. FFmpeg is needed
for loudness/true-peak measurements; missing/disabled checks are disclosed. The
review reads markers saved **in the selected WAV**, not unsaved waveform edits.
Save your reviewed copy, then select that file if you want those edits reviewed.

## 4. Preview, then send

1. In **Preview & Send**, inspect the request messages. They include the selected
   script, transcript, saved marker labels/times and local QC findings.
2. Check that the script really belongs to this recording and that you have
   permission to send this text to a cloud service.
3. Tick the consent checkbox, then click **Send Previewed Text for AI Review**.

No WAV or PDF file is uploaded. However, script/transcript text and QC details do
leave your computer when you click Send. The API key is sent to OpenRouter for
authentication, not placed inside the model prompt. The provider exclusion option
requests providers that do not collect prompts; this is not a claim that processing
is offline. Read [OpenRouter's privacy information](https://openrouter.ai/privacy)
and the selected provider's terms. Leave the option enabled unless you understand
the effect of changing it. Requests are not silently retried or rerouted to paid models.

## 5. Check the findings

- Read the summary and limitations in **Findings**.
- Each suggestion references supplied evidence (script `S`, transcript `T`, marker
  `M`, or local QC `Q`). Select timed evidence and click **Play Evidence** to hear
  approximately eight seconds around it. Pasted text has no trustworthy timestamp.
- A transcription error can look like a missing or wrong Bible verse. Names,
  repeated phrases, headings and low-resource languages require special care.
- If you do not know the language, ask a fluent reviewer to validate suspected
  errors. An English AI explanation cannot replace that confirmation.
- AI never changes the audio, markers, measurement values or QC pass/fail result.
  It does not generate verified replacement marker times.
- **Export Review JSON** saves a local report with its evidence and actual model
  name. The export contains chapter text, so share it deliberately. It has no key.

“No issues suggested” is **not** a pass. Malformed, incomplete or unsupported AI
responses are rejected, not treated as successful validation.

## Common problems

| Message/problem | What to do |
| --- | --- |
| No chapter selected | Click a WAV row in Chapters & QC, then reopen AI Review. |
| API key rejected | Paste a valid OpenRouter key, not a ChatGPT password/subscription. |
| Rate limit reached | Wait and try later, or select another available free model. |
| No suitable provider | Choose a different free model; privacy filters can reduce availability. |
| Chapter too large/context rejected | Use a shorter script/transcript selection and check the preview. The app never silently truncates your chapter. |
| No transcript | Only QC/marker structure can be explained; spoken content is not verified. |
| Incorrect Assamese results | Inspect the extracted script and local transcript first; do not assume the recording is wrong. |
| Connection timeout | Check internet access and retry deliberately. The earlier request may already have reached the provider. |
| Review window cannot close yet | Wait for the current operation. Local transcription can take several minutes. |

## For the developer

The client uses Python's standard HTTP library; no OpenRouter SDK or extra model
download is needed for pasted-text reviews. Model files remain optional local
downloads. Automated tests mock cloud replies; they do not establish real model
accuracy. Before releasing, test with your own key and a short, consented chapter,
then test the newly built Windows and Mac installers. Existing installed builds
do not gain this feature until you rebuild and distribute an update.
