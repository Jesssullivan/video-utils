-- Type-level tests of the edition rule, bed clearance and the persona label (docs/spec/NARRATED_VIDEO.md).
-- `dhall type` fails if any assertion is false. Each ClientVoiceOnly refusal is asserted alone at each of
-- its three points (Plan, Place, DeliverCheck); narrate/dhall/check.py ports the same rule to Python and
-- narrate/tests/test_narrated_video_types.py asserts the port against this table.
let Edition = ./Edition.dhall

let MusicBed = ./MusicBed.dhall

let NarratedVideo = ./NarratedVideo.dhall

let E = Edition.Edition

let P = Edition.Point

let C = Edition.Code

let V = Edition.Verdict

let clean = Edition.clean

let refusedAt =
      \(p : Edition.Point) ->
      \(codes : List Edition.Code) ->
        V.Refused { point = p, codes }

let voicePlan =
        assert
      :     Edition.check
              P.Plan
              E.ClientVoiceOnly
              (clean // { syntheticVoice = True })
        ===  refusedAt P.Plan [ C.VoiceRefused ]

let voicePlace =
        assert
      :     Edition.check
              P.Place
              E.ClientVoiceOnly
              (clean // { syntheticVoice = True })
        ===  refusedAt P.Place [ C.VoiceRefused ]

let voiceDeliver =
        assert
      :     Edition.check
              P.DeliverCheck
              E.ClientVoiceOnly
              (clean // { syntheticVoice = True })
        ===  refusedAt P.DeliverCheck [ C.VoiceRefused ]

let avatarPlan =
        assert
      :     Edition.check P.Plan E.ClientVoiceOnly (clean // { avatar = True })
        ===  refusedAt P.Plan [ C.PipRefused ]

let pipPlace =
        assert
      :     Edition.check P.Place E.ClientVoiceOnly (clean // { pip = True })
        ===  refusedAt P.Place [ C.PipRefused ]

let pipDeliver =
        assert
      :     Edition.check
              P.DeliverCheck
              E.ClientVoiceOnly
              (clean // { pip = True })
        ===  refusedAt P.DeliverCheck [ C.PipRefused ]

let bedPlan =
        assert
      :     Edition.check P.Plan E.ClientVoiceOnly (clean // { bed = True })
        ===  refusedAt P.Plan [ C.BedRefused ]

let bedPlace =
        assert
      :     Edition.check P.Place E.ClientVoiceOnly (clean // { bed = True })
        ===  refusedAt P.Place [ C.BedRefused ]

let bedDeliver =
        assert
      :     Edition.check
              P.DeliverCheck
              E.ClientVoiceOnly
              (clean // { bed = True })
        ===  refusedAt P.DeliverCheck [ C.BedRefused ]

let clearedBedAdmitted =
        assert
      :     Edition.check
              P.DeliverCheck
              E.ClientVoiceOnly
              (clean // { bed = True, bedCleared = True })
        ===  V.Admitted

let voiceOnlyAdmitted =
      assert : Edition.check P.Plan E.ClientVoiceOnly clean === V.Admitted

let allCodesInOrder =
        assert
      :     Edition.check
              P.Place
              E.ClientVoiceOnly
              { syntheticVoice = True
              , avatar = True
              , pip = True
              , bed = True
              , bedCleared = False
              }
        ===  refusedAt P.Place [ C.VoiceRefused, C.PipRefused, C.BedRefused ]

let everything =
      { syntheticVoice = True
      , avatar = True
      , pip = True
      , bed = True
      , bedCleared = False
      }

let internalAllowsAll =
      assert : Edition.check P.Plan E.Internal everything === V.Admitted

let ownContentAllowsAll =
        assert
      : Edition.check P.DeliverCheck E.OwnContent everything === V.Admitted

let bed
    : MusicBed.Type
    = { id = "probe-bed"
      , layers = [] : List MusicBed.Layer
      , licence =
        { termsRef = "probe"
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
        , rulingRef = "probe"
        }
      }

let pdf = Some "probe-pdf-digest"

let clear = MusicBed.ContentId.Clear { clear = "probe-receipt" }

let notClearedWithoutPdf =
        assert
      :     MusicBed.licenceCleared
              (bed // { licence = bed.licence // { contentIdCheck = clear } })
        ===  False

let notClearedWithoutContentId =
        assert
      :     MusicBed.licenceCleared
              (bed // { licence = bed.licence // { certifiedPdfSha256 = pdf } })
        ===  False

let notClearedWhenClaimed =
        assert
      :     MusicBed.licenceCleared
              (     bed
                //  { licence =
                            bed.licence
                        //  { certifiedPdfSha256 = pdf
                            , contentIdCheck =
                                MusicBed.ContentId.Claimed { claimed = "probe" }
                            }
                    }
              )
        ===  False

let clearedBed =
          bed
      //  { licence =
                  bed.licence
              //  { certifiedPdfSha256 = pdf, contentIdCheck = clear }
          }

let licenceClearedWithBoth =
      assert : MusicBed.licenceCleared clearedBed === True

let d = NarratedVideo.defaults

let job
    : NarratedVideo.Type
    = { id = "probe-job"
      , edition = E.ClientVoiceOnly
      , base =
          NarratedVideo.Base.Card
            { card =
              { colour = "#000000"
              , size = d.size
              , fps = d.fps
              , tailS = d.tailS
              }
            }
      , segments = [] : List NarratedVideo.Segment
      , avatar = None NarratedVideo.Avatar
      , music = None NarratedVideo.Music
      , captions = d.captions
      , labels =
        { persona = None Text, personaCue = "probe", extraNotice = None Text }
      , delivery = d.delivery
      }

let segment =
      { id = "s"
      , narrateJob = "probe"
      , scriptSha256 = "probe"
      , anchor = NarratedVideo.Anchor.Auto
      , avatar = True
      }

let withMusic = job // { music = Some (d.music // { bed = "probe-bed" }) }

let listened =
          withMusic
      //  { delivery = d.delivery // { voiceOnlyListen = Some "probe-listen" } }

let planVoiceOnlyJob =
      assert : NarratedVideo.plan job (None MusicBed.Type) === V.Admitted

let planSyntheticSegment =
        assert
      :     NarratedVideo.plan
              (job // { segments = [ segment ] })
              (None MusicBed.Type)
        ===  refusedAt P.Plan [ C.VoiceRefused ]

let planAvatarBlockWithoutSegments =
        assert
      :     NarratedVideo.plan
              (job // { avatar = Some d.avatar })
              (None MusicBed.Type)
        ===  refusedAt P.Plan [ C.PipRefused ]

let planBedUncleared =
        assert
      :     NarratedVideo.plan withMusic (Some bed)
        ===  refusedAt P.Plan [ C.BedRefused ]

let planBedClearedWithoutListen =
        assert
      :     NarratedVideo.plan withMusic (Some clearedBed)
        ===  refusedAt P.Plan [ C.BedRefused ]

let planBedListenedButUncleared =
        assert
      :     NarratedVideo.plan listened (Some bed)
        ===  refusedAt P.Plan [ C.BedRefused ]

let planBedClearedAndListened =
      assert : NarratedVideo.plan listened (Some clearedBed) === V.Admitted

let internalDefaultsAdmitEverything =
        assert
      :     NarratedVideo.plan
              (     withMusic
                //  { edition = d.edition
                    , segments = [ segment ]
                    , avatar = Some d.avatar
                    }
              )
              (Some bed)
        ===  V.Admitted

let avatarNeedsPersona =
        assert
      :     NarratedVideo.personaLabelled
              (job // { segments = [ segment ], avatar = Some d.avatar })
        ===  False

let avatarWithPersona =
        assert
      :     NarratedVideo.personaLabelled
              (     job
                //  { segments = [ segment ]
                    , avatar = Some d.avatar
                    , labels = job.labels // { persona = Some "probe-persona" }
                    }
              )
        ===  True

let avatarOffNeedsNoPersona =
        assert
      :     NarratedVideo.personaLabelled
              (     job
                //  { segments = [ segment // { avatar = False } ]
                    , avatar = Some d.avatar
                    }
              )
        ===  True

let defaultsMatchNv2 =
        assert
      :     { edition = d.edition
            , channels = d.delivery.channels
            , lufs = d.delivery.targetLufs
            , peak = d.delivery.truePeakDbtp
            , drift = d.delivery.driftLu
            , below = d.music.bedBelowVoiceLu
            , duck = d.music.duckDb
            , fadeIn = d.music.fadeInS
            , fadeOut = d.music.fadeOutS
            }
        ===  { edition = E.Internal
             , channels = NarratedVideo.Channels.Mono
             , lufs = -16.0
             , peak = -1.5
             , drift = 0.5
             , below = 20.0
             , duck = 7.0
             , fadeIn = 3.0
             , fadeOut = 5.0
             }

in  True
