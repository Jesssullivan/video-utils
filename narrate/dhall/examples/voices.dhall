-- A fixture voice: the generated one-second 375 Hz sine and its fixture transcript. No real clip exists.
let Consent = ../Consent.dhall

let Voice = ../Voice.dhall

in    [ { id = "voice-fixture-sine"
        , consentId = "consent-fixture-sine"
        , scope = Consent.Scope.OwnContent
        , refClipSha256 =
            "ccf6a2e994d21813138697ee3c33dc5459ed6b23778e8b98c44bf6f246e872a0"
        , refClipSeconds = 1.0
        , refClipSampleRateHz = 24000
        , refTextSha256 =
            "5987c41d1d7c41f66a5d0ae2a044b76accf8f7c5877a3f593223ac6b43f5712b"
        , allowedEngines = [ "fake-sine" ]
        , fixture = True
        }
      ]
    : List Voice.Type
