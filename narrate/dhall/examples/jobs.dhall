-- An example job: the fixture script, the fake engine and the fixture voice. The gate values are
-- placeholders, not calibrated thresholds (gates.calibrated = False); W3 measures them.
let Consent = ../Consent.dhall

let Job = ../Job.dhall

let lexical
    : Job.Lexical
    = { release = "xoxd-lexical@0.7.0"
      , commit = "a1f580147d7b95b14e6a2085205021f91fd9e221"
      , lexiconSha256 =
          "dedfa123ed7f4d4e5d528097a62589330e71f9be7c7baa9f97e5cb0678c39c84"
      , promptDigestSha256 =
          "20b2b3e744a3d2462abeee08ae50f0bf0e2a32cb9cbba3dc7ee9a6149a58aa3f"
      , valeRegister = "narration"
      , valeRegisterSha256 =
          "d490bdc794832b6842f89fb758bb4a265a74c660080222d119a6f8931ffacc2a"
      , rewriteCheck = True
      }

in    [ { id = "job-fixture-fake"
        , input = Job.Input.Markdown
        , inputSha256 =
            "93f7f4183b4b6ccec0c3ef2c83cca16dcb0ec4a929d55941193ab84f4f355d3a"
        , scope = Consent.Scope.OwnContent
        , confidential = False
        , allowHosted = False
        , lexical
        , pronunciation = "narrate-en-example"
        , voice = "voice-fixture-sine"
        , speakers = [] : List Job.Speaker
        , engine = "fake-sine"
        , seed = 0
        , chunkMaxCodepoints = 300
        , gates =
          { maxChunkWer = 0.1, minSim = 0.0, maxTakes = 3, calibrated = False }
        , post =
          { loudnessLufs = -16.0
          , truePeakDbtp = -1.5
          , loudnessToleranceLu = 0.5
          , fitMaxStretch = 0.08
          , sentencePauseMs = 250
          , paragraphPauseMs = 600
          }
        , audio = Job.AudioFormat.Wav
        , captions = [ Job.CaptionFormat.Srt, Job.CaptionFormat.Vtt ]
        , narrationEdl = True
        }
      ]
    : List Job.Type
