-- An example job: the fixture script, the fake engine and the fixture voice. The gate values are
-- placeholders, not calibrated thresholds (gates.calibrated = False); W3 measures them.
let Job = ../Job.dhall

let lexical
    : Job.Lexical
    = { release = "xoxd-lexical@0.2.0"
      , commit = "83911757c9a5f9933345cdb11c8731637c548c11"
      , lexiconSha256 =
          "4e1373fda976ad48ad2676fc2f554b6d8acd47a69aa1c21bf1d06d3af43b4873"
      , promptDigestSha256 =
          "a1113fa9c0bba403c9b738dba102cce59bba5151316932f1e921dc6e0c9b5d4a"
      , valeRegister = "slides"
      , valeRegisterSha256 =
          "f3848629e44bf1f84a4bec00d38972f0208ca1e25424e6e5d45f767f573f4b0b"
      , rewriteCheck = True
      }

in    [ { id = "job-fixture-fake"
        , input = Job.Input.Markdown
        , inputSha256 =
            "93f7f4183b4b6ccec0c3ef2c83cca16dcb0ec4a929d55941193ab84f4f355d3a"
        , confidential = False
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
