-- A fixture music bed: two generated E-major sine loops (narrate/dhall/check.py), never a recording or a
-- licensed loop. It has no licence PDF and no Content ID result, so it is not cleared: a delivery under
-- either client edition refuses it. Real bed records, loops and licence PDFs live in the private store.
let MusicBed = ../MusicBed.dhall

in    [ { id = "bed-fixture-emaj"
        , layers =
          [ { sha256 =
                "233a01a6cd3d2e27589f1d2ddb6f3c36bcf4b9e4f8c8ec9a28438cfc027311a8"
            , bytes = 192044
            , rateHz = 48000
            , channels = 1
            , source = MusicBed.Source.Fixture
            , bpm = Some 120.0
            , key = Some "E major"
            , tempoFactor = 1.0
            , gainDb = 0.0
            }
          , { sha256 =
                "41b56340fe586a8880445e4e56d4a009ccac5336b34283bca9ab9b4bfa34e01b"
            , bytes = 288044
            , rateHz = 48000
            , channels = 1
            , source = MusicBed.Source.Fixture
            , bpm = None Double
            , key = Some "E major"
            , tempoFactor = 1.0
            , gainDb = -6.0
            }
          ]
        , licence =
          { termsRef = "fixture: generated sine loops, no licence applies"
          , termsReadOn = None Text
          , attributionRequired = False
          , attributionText = None Text
          , certifiedPdfSha256 = None Text
          , contentIdCheck = MusicBed.ContentId.NotRun
          }
        , acquisition =
          { acquiredBy = MusicBed.Acquirer.Operator
          , date = "2026-10-27"
          , creditsSpent = 0
          , rulingRef = "TIN-7476 comment 9db389dc (NV-3)"
          }
        }
      ]
    : List MusicBed.Type
