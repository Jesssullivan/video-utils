-- A music bed: 2 or 3 loops layered and arranged under narration (docs/spec/NARRATED_VIDEO.md, "Music bed").
-- Real records, loops, licence PDFs and bed audio live in the private store, found by sha256. This
-- repository holds the type and a fixture bed of generated sine loops (narrate/dhall/check.py).
--
-- acquiredBy is Operator (NV-3, TIN-7476 comment 9db389dc), or Agent with the campaign whose agent spent the
-- credits (TIN-7125 comment e552e569). The payload is keyed ({ agent = ... }) so the JSON keeps the tag, and
-- an agent's record cannot leave its campaign out. narrate/video/bed_select.py refuses one on a client
-- edition or on a job root that campaign does not hold, so NV-3 stands for every other job.
-- tempoFactor is from 0.5 to 2.0. A loop is never used alone as-is; the bed is an arrangement.
-- ContentId payloads name the check's receipt, keyed ({ clear = ... }) so the JSON keeps the tag.
-- Licence.termsRef names the vendor terms the operator read; the record is private.
-- licenceCleared is the licence half of bed clearance: a certified licence PDF digest and a clear Content ID
-- result. The voice-only listen pass belongs to the delivery (NarratedVideo Delivery.voiceOnlyListen).
let Source = < Splice | YoutubeAudioLibrary | SelfMade | Fixture >

let Layer =
      { sha256 : Text
      , bytes : Natural
      , rateHz : Natural
      , channels : Natural
      , source : Source
      , bpm : Optional Double
      , key : Optional Text
      , tempoFactor : Double
      , gainDb : Double
      }

let ContentId =
      < NotRun | Clear : { clear : Text } | Claimed : { claimed : Text } >

let Licence =
      { termsRef : Text
      , termsReadOn : Optional Text
      , attributionRequired : Bool
      , attributionText : Optional Text
      , certifiedPdfSha256 : Optional Text
      , contentIdCheck : ContentId
      }

let Acquirer = < Operator | Agent : { agent : Text } >

let Acquisition =
      { acquiredBy : Acquirer
      , date : Text
      , creditsSpent : Natural
      , rulingRef : Text
      }

let T =
      { id : Text
      , layers : List Layer
      , licence : Licence
      , acquisition : Acquisition
      }

let isSome =
      \(a : Type) ->
      \(o : Optional a) ->
        merge { None = False, Some = \(_ : a) -> True } o

let contentIdClear =
      \(c : ContentId) ->
        merge
          { NotRun = False
          , Clear = \(_ : { clear : Text }) -> True
          , Claimed = \(_ : { claimed : Text }) -> False
          }
          c

let licenceCleared =
      \(b : T) ->
            isSome Text b.licence.certifiedPdfSha256
        &&  contentIdClear b.licence.contentIdCheck

in  { Type = T
    , Source
    , Layer
    , ContentId
    , Licence
    , Acquirer
    , Acquisition
    , licenceCleared
    }
