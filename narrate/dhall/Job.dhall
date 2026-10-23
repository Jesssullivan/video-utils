-- One narration job: what to read, through which pinned lexical release, in which voice, on which
-- engine, and the gates every chunk must pass (docs/spec/NARRATE.md, "Dataflow").
let Input = < PlainText | Markdown | Srt | Vtt | CondenseWords | Dialog >

let AudioFormat = < Wav | Flac >

let CaptionFormat = < Srt | Vtt >

let Lexical =
      { release : Text
      , commit : Text
      , lexiconSha256 : Text
      , promptDigestSha256 : Text
      , valeRegister : Text
      , valeRegisterSha256 : Text
      , rewriteCheck : Bool
      }

let Gates =
      { maxChunkWer : Double
      , minSim : Double
      , maxTakes : Natural
      , calibrated : Bool
      }

let Post =
      { loudnessLufs : Double
      , truePeakDbtp : Double
      , loudnessToleranceLu : Double
      , fitMaxStretch : Double
      , sentencePauseMs : Natural
      , paragraphPauseMs : Natural
      }

let Speaker = { speaker : Text, voice : Text }

let T =
      { id : Text
      , input : Input
      , inputSha256 : Text
      , confidential : Bool
      , lexical : Lexical
      , pronunciation : Text
      , voice : Text
      , speakers : List Speaker
      , engine : Text
      , seed : Natural
      , chunkMaxCodepoints : Natural
      , gates : Gates
      , post : Post
      , audio : AudioFormat
      , captions : List CaptionFormat
      , narrationEdl : Bool
      }

in  { Type = T
    , Input
    , AudioFormat
    , CaptionFormat
    , Lexical
    , Gates
    , Post
    , Speaker
    }
