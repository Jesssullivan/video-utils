-- The only engine instance in git: the deterministic fake used by tests. It needs no GPU, no weights
-- and no network, and it never runs a real voice.
let Engine = ../Engine.dhall

let fake
    : Engine.Type
    = { id = "fake-sine"
      , profile = Engine.Profile.Fake
      , backend = Engine.Backend.Fake
      , endpoint = "fake://sine"
      , model = "fake-sine-v1"
      , hfRepo = None Text
      , hfRevision = None Text
      , sha256 = [] : List Text
      , licence = "repository licence; no weights"
      , licenceNotice = None Text
      , vramGiB = None Double
      , sampleRateHz = 24000
      , hosted = False
      , estateControlled = True
      , confidentialAllowed = True
      }

let _policy = assert : Engine.mayRunConfidential fake === True

in  [ fake ]
