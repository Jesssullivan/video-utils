-- One narrated-video job: a base picture, narrated segments, an optional kitpip avatar, an optional music bed,
-- captions, labels and a delivery target (docs/spec/NARRATED_VIDEO.md). A job holds digests and store ids,
-- never paths. The executor reads its dhall-to-json render, never Dhall, at stage time.
--
-- Real jobs, bed records and resolved pins live in the private store. examples/narrated-videos.dhall holds
-- the only instances in git, bound to synthetic fixtures (narrate/dhall/check.py).
--
-- Base.Deck: a slide-deck result assembled outside this repository, imported by digest. `producer` is
--   recorded, never executed. tightenEditsSha256 names the dead-air edits the deck applied, if any. Tighten is
--   off for synthetic narration (NV-2): place checks every take against its narrate run, so an edited take
--   is unbound (voice_stem_unbound).
-- Segment.narrateJob: a narrate Job id in the private store (examples: job-fixture-fake). Every segment is a
--   narrate render, so any segment is a synthetic voice. Segment.avatar False hides the overlay for that
--   segment (dense screens).
-- Avatar.external: "kitpip", resolved through the private pin record. rig None takes the pin's default rig.
--   width is a fraction of the base width, 0.10 to 0.30.
-- Music levels (NV-2): the un-ducked bed sits bedBelowVoiceLu (about 20) below the narration's integrated
--   loudness. The sidechain ducks it a further duckDb (6 to 8; refused above 12) under the whole foreground,
--   voice and kept clip sound alike. Fades are 3 s in and 5 s out.
-- Labels.persona: required when an avatar is on, and equal to the consent record's persona when a
--   segment's voice has one. personaCue opens the captions. extraNotice is appended to description.txt and
--   never replaces it.
-- Delivery: narration is measured at targetLufs integrated and the whole mix is never loudness-normalised.
--   One limiter, in mix. driftLu (at most 0.5) and truePeakDbtp (at most -1.5) are hard gates. upload arms
--   the licence and Content ID gates. voiceOnlyListen names the receipt of a voice-only listen pass, one of
--   the three conditions a ClientVoiceOnly delivery needs before it may carry a bed.
-- Union payloads are records keyed by the constructor's name ({ still = ... }, { atSeconds = ... }), because
--   dhall-to-json drops union tags: the rendered JSON stays unambiguous ({"still": {...}}, "Auto").
-- planLeaves and plan: the Plan point of Edition.check. `bed` is the resolved private record that the job's
--   music names, if any. At Plan, pip is any avatar block, so a ClientVoiceOnly job that configures an
--   avatar with every segment switched off is still refused.
let Edition = ./Edition.dhall

let MusicBed = ./MusicBed.dhall

let Rate = { num : Natural, den : Natural }

let Size = { w : Natural, h : Natural }

let Corner = < BR | BL | TR | TL >

let Still = { sha256 : Text, size : Size, fps : Rate, tailS : Double }

let Card = { colour : Text, size : Size, fps : Rate, tailS : Double }

let Video = { sha256 : Text, keepBaseAudio : Bool }

let Deck =
      { producer : Text
      , videoSha256 : Text
      , timelineSha256 : Text
      , stemsSha256 : Text
      , tightenEditsSha256 : Optional Text
      }

let Base =
      < Still : { still : Still }
      | Card : { card : Card }
      | Video : { video : Video }
      | Deck : { deck : Deck }
      >

let Anchor =
      < Auto | AtSeconds : { atSeconds : Double } | Page : { page : Text } >

let Segment =
      { id : Text
      , narrateJob : Text
      , scriptSha256 : Text
      , anchor : Anchor
      , avatar : Bool
      }

let Avatar =
      { external : Text
      , rig : Optional Text
      , rigRevisionSha256 : Optional Text
      , renderSize : Natural
      , corner : Corner
      , width : Double
      , marginPx : Natural
      }

let DuckMode = < Sidechain | EdlEnvelope >

let Music =
      { bed : Text
      , bedBelowVoiceLu : Double
      , duckMode : DuckMode
      , duckDb : Double
      , attackMs : Natural
      , releaseMs : Natural
      , fadeInS : Double
      , fadeOutS : Double
      , tailS : Double
      }

let Captions = { soft : Bool, burn : Bool, srt : Bool, vtt : Bool }

let Labels =
      { persona : Optional Text
      , personaCue : Text
      , extraNotice : Optional Text
      }

let Profile = < Web1080p30 | Talk | Contingency >

let Channels = < Mono | Stereo >

let Delivery =
      { profile : Profile
      , targetLufs : Double
      , truePeakDbtp : Double
      , driftLu : Double
      , channels : Channels
      , upload : Bool
      , handoff : Bool
      , voiceOnlyListen : Optional Text
      }

let T =
      { id : Text
      , edition : Edition.Type
      , base : Base
      , segments : List Segment
      , avatar : Optional Avatar
      , music : Optional Music
      , captions : Captions
      , labels : Labels
      , delivery : Delivery
      }

let isSome =
      \(a : Type) ->
      \(o : Optional a) ->
        merge { None = False, Some = \(_ : a) -> True } o

let anySegmentAvatar =
      \(job : T) ->
        List/fold
          Segment
          job.segments
          Bool
          (\(s : Segment) -> \(acc : Bool) -> s.avatar || acc)
          False

let avatarOn = \(job : T) -> isSome Avatar job.avatar && anySegmentAvatar job

let syntheticVoice =
      \(job : T) -> Natural/isZero (List/length Segment job.segments) == False

let bedCleared =
      \(job : T) ->
      \(bed : Optional MusicBed.Type) ->
            merge
              { None = False
              , Some = \(b : MusicBed.Type) -> MusicBed.licenceCleared b
              }
              bed
        &&  isSome Text job.delivery.voiceOnlyListen

let planLeaves =
      \(job : T) ->
      \(bed : Optional MusicBed.Type) ->
        { syntheticVoice = syntheticVoice job
        , avatar = avatarOn job
        , pip = isSome Avatar job.avatar
        , bed = isSome Music job.music
        , bedCleared = bedCleared job bed
        }

let plan =
      \(job : T) ->
      \(bed : Optional MusicBed.Type) ->
        Edition.check Edition.Point.Plan job.edition (planLeaves job bed)

let personaLabelled =
      \(job : T) -> avatarOn job == False || isSome Text job.labels.persona

let defaults =
      { edition = Edition.Edition.Internal
      , fps = { num = 30, den = 1 }
      , size = { w = 1920, h = 1080 }
      , tailS = 1.0
      , avatar =
        { external = "kitpip"
        , rig = None Text
        , rigRevisionSha256 = None Text
        , renderSize = 512
        , corner = Corner.BR
        , width = 0.22
        , marginPx = 32
        }
      , music =
        { bedBelowVoiceLu = 20.0
        , duckMode = DuckMode.Sidechain
        , duckDb = 7.0
        , attackMs = 50
        , releaseMs = 400
        , fadeInS = 3.0
        , fadeOutS = 5.0
        , tailS = 5.0
        }
      , captions = { soft = True, burn = False, srt = True, vtt = True }
      , delivery =
        { profile = Profile.Web1080p30
        , targetLufs = -16.0
        , truePeakDbtp = -1.5
        , driftLu = 0.5
        , channels = Channels.Mono
        , upload = False
        , handoff = False
        , voiceOnlyListen = None Text
        }
      }

in  { Type = T
    , Rate
    , Size
    , Corner
    , Still
    , Card
    , Video
    , Deck
    , Base
    , Anchor
    , Segment
    , Avatar
    , DuckMode
    , Music
    , Captions
    , Labels
    , Profile
    , Channels
    , Delivery
    , avatarOn
    , syntheticVoice
    , bedCleared
    , planLeaves
    , plan
    , personaLabelled
    , defaults
    }
