-- An example job: the fixture script, the fake engine and the fixture voice. The gate values are
-- placeholders, not calibrated thresholds (gates.calibrated = False); W3 measures them.
let Consent = ../Consent.dhall

let Job = ../Job.dhall

let lexical
    : Job.Lexical
    = { release = "xoxd-lexical@0.8.0"
      , commit = "0828ab0222189cc51d4f2e94e2a908dc3be71bcc"
      , lexiconSha256 =
          "dccccea4085162b11cc3f0ee1ec0df9e77d9f8b8a823b3f9dbe47cea35bb3919"
      , promptDigestSha256 =
          "058a5982d75c17aa30512134649c3d3d1b2a71d80a009a58591496eb78cc8d5f"
      , valeRegister = "narration"
      , valeRegisterSha256 =
          "0336ea3d4c44c2e87953b3f630c2f1f12a96d7bb06c06e2476897900e4512a63"
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
