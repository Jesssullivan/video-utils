-- An example job: the fixture script, the fake engine and the fixture voice. The gate values are
-- placeholders, not calibrated thresholds (gates.calibrated = False); W3 measures them.
let Consent = ../Consent.dhall

let Job = ../Job.dhall

let lexical
    : Job.Lexical
    = { release = "xoxd-lexical@0.3.0"
      , commit = "a054ff37082d3f89391d90de5665f0799cb7c87e"
      , lexiconSha256 =
          "0337b0dcfefda437e6524310c8ba76f37d95aaf97f6ae1f55810b7282b2d5d10"
      , promptDigestSha256 =
          "c51d15e97fccf5c0b479a7864bd0ef5cfb7c099da51f56d5d13be741680c01b0"
      , valeRegister = "narration"
      , valeRegisterSha256 =
          "380274db85557f01b8293fe308bcff6e3ba4233939fe8949e3082f6512d2c076"
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
