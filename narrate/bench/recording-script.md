# Narrate v0: reference and consent recording script

Written 2026-10-22 for the narrate engine bench
([plan](../../docs/agent-notes/2026-10-22-narrate-bench-plan.md)). Two separate clips are recorded: a
**consent clip** first, then a **reference clip**. Neither clip, nor any transcript of the consent clip, is
ever committed to this public repository. Both stay in the private voice store with their sha256 values,
and only the hashes and the consent id appear in bench receipts.

v0 clones one voice: the operator's own. Nobody else reads these scripts for cloning.

## Recording guidance (both clips)

- **Room.** The quietest room available. Switch off fans, air purifiers and the box fan for the
  duration of the recording; close windows and doors. Soft furnishings help; a bare room echoes.
- **Distance.** Mouth about 20 cm from the microphone, slightly off axis (aim the mic at the chin,
  not straight into the mouth) to keep plosives down. Keep the distance constant.
- **Format.** 48 kHz, 24-bit (or 16-bit) PCM WAV, mono if the interface allows it. No compression,
  no MP3/AAC export.
- **No processing.** Turn off noise suppression, automatic gain, voice isolation, EQ, compression
  and reverb in the recording app and the operating system. Set the input gain so normal speech
  peaks around -12 dBFS and never clips.
- **Room tone.** Before speaking, stay silent for about 2 seconds so the clip carries a little room
  tone. Stay silent for about 1 second after the last word.
- **Delivery.** Natural narration: the voice you would use reading a short article aloud to a
  colleague. Not a radio announcer voice, not a whisper. Normal pace; pause briefly at full stops.
- **Retakes.** If you stumble, stop and record the whole clip again from the start. Do not edit
  takes together. Keep the best complete take and note which take number it was.
- **Device.** Use the same microphone and position for both clips, and note the microphone and
  app names in the private voice record (not in this repository).

## Clip 1: consent statement (separate clip, recorded first)

Read this exactly, filling in the bracketed parts aloud (about 15 seconds):

> My name is [full name]. Today is [day, month and year]. I consent to this recording being used as
> a reference to synthesise my own voice for narration in my projects. I can withdraw this consent
> at any time.

This is the text printed for the operator's 2026-10-22 session. Narrate labels its output as
synthetic and keeps reference clips private regardless of what the statement says.

After the recording: compute the clip's sha256, store the clip in the private voice store, and create
the consent record (consent id, speaker, granted-at date, revocable: true, evidence sha256,
synthetic label required: true). The bench refuses any reference clip without a matching consent id.

## Clip 2: reference read-aloud (25 to 30 seconds)

Read this at a natural pace, twice, as two separate takes. It is about 75 words and should take 25 to
30 seconds with the pauses. This is the text printed for the operator's 2026-10-22 session.

> Every recording tells a story, even before anyone speaks. Here, the first few seconds are quiet:
> a fan hums, a chair creaks, and then the guitar comes in, low and heavy. Over the next twelve
> minutes we'll measure the timing, check each phrase, and fix what the microphone missed. It's
> not magic, just careful work. So grab a coffee, turn the volume up a little, and let's see what
> we can hear together.

After the recording:

1. Listen once on headphones. Reject the take if there is clipping, a fan or traffic noise, a
   stumble, or a word that differs from the script.
2. Produce the **verified transcript**: start from the script text above, and change it only where
   the take differs from the script (for example a contraction you actually said). A person checks
   it against the audio; a whisper transcript can help but is never accepted unreviewed, because
   ICL cloning degrades sharply with a wrong reference transcript.
3. Compute sha256 values for the clip and the verified transcript, and record them in the private
   voice record with the consent id from clip 1.
4. If an engine prefers a shorter reference (for example 10 seconds), the bench cuts it from this
   clip at a sentence boundary and records the cut points and the new hash; the source clip is
   never overwritten.
