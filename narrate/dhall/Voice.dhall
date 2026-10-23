-- A voice: one reference clip and its verified transcript, bound by sha256 and to a consent record.
-- The registry never holds a path. The clip and transcript are found by digest in a store outside git.
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
      }

in  { Type = T }
