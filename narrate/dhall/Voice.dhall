-- A voice: one reference clip and its verified transcript, bound by sha256 and to a consent record.
-- The registry never holds a path. The clip and transcript are found by digest in a store outside git.
-- tempo: a pitch-preserving tempo factor applied to every take after synthesis, before QA and the timing fit
-- (narrate/tempo.py). None speaks at 1.0. A value is from 0.5 to 2.0.
let Consent = ./Consent.dhall

let T =
      { id : Text
      , consentId : Text
      , scope : Consent.Scope
      , refClipSha256 : Text
      , refClipSeconds : Double
      , refClipSampleRateHz : Natural
      , refTextSha256 : Text
      , allowedEngines : List Text
      , fixture : Bool
      , tempo : Optional Double
      }

in  { Type = T, default.tempo = None Double }
