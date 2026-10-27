-- A fixture consent record bound to a generated statement (narrate/dhall/check.py). It grants nothing
-- for any real speaker. Real consent records live outside git with their evidence.
let Consent = ../Consent.dhall

in    [ { id = "consent-fixture-sine"
        , speaker = "fixture"
        , grantedAt = "2026-10-22"
        , grantedBy = "fixture"
        , scopes = [ Consent.Scope.OwnContent ]
        , hostedAllowed = False
        , revocable = True
        , revokedAt = None Text
        , evidenceSha256 =
            "7564736f7cb7bb107e7eb648370100d2ba2fe46f2223a84cd887ba94f4cfb7a9"
        , syntheticLabelRequired = True
        , persona = None Text
        }
      ]
    : List Consent.Type
