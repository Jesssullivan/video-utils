-- A fixture voice: the generated ten-second 375 Hz sine and its fixture transcript. No real clip exists.
let Consent = ../Consent.dhall

let Voice = ../Voice.dhall

in    [ { id = "voice-fixture-sine"
        , consentId = "consent-fixture-sine"
        , scope = Consent.Scope.OwnContent
        , refClipSha256 =
            "c6b8094426ba0044cfead8d2d5055a94576b07493d724c851dc558801b539a68"
        , refClipSeconds = 10.0
        , refClipSampleRateHz = 24000
        , refTextSha256 =
            "5987c41d1d7c41f66a5d0ae2a044b76accf8f7c5877a3f593223ac6b43f5712b"
        , allowedEngines = [ "fake-sine" ]
        , fixture = True
        }
      ]
    : List Voice.Type
