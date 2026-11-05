-- One narrated-video job: a base picture, narrated segments, an optional kitpip avatar, an optional music bed,
-- captions, labels and a delivery target (docs/spec/NARRATED_VIDEO.md). A job holds digests and store ids,
-- never paths. The executor reads its dhall-to-json render, never Dhall, at stage time.
--
-- Real jobs, bed records and resolved pins live in the private store. examples/narrated-videos.dhall holds
-- the only instances in git, bound to synthetic fixtures (narrate/dhall/check.py).
--
-- Base.Deck: a slide-deck result assembled outside this repository, imported by digest. `producer` is
--   recorded, never executed. tightenEditsSha256 names the dead-air edits the deck applied, if any.
-- Tighten: off by default for synthetic narration (NV-2). A project may set tighten.enabled True; the deck
--   project does, under its rulings 58 to 60. tightenAdmitted refuses tighten edits on narrate segments while tighten
--   is off (tighten_on_synthetic). With tighten on, place binds each tightened take through the deck's
--   stems.json: the edits digest must equal tightenEditsSha256 and the pre-tighten take digest must equal the
--   narrate run's output, or place refuses voice_stem_unbound.
-- Segment.narrateJob: a narrate Job id in the private store (examples: job-fixture-fake). Every segment is a
--   narrate render, so any segment is a synthetic voice. Segment.avatar False hides the overlay for that
--   segment (dense screens).
-- Avatar.external: "kitpip", resolved through the private pin record. rig None takes the pin's default rig.
--   Or "vrm" (SPR-128, a draft): rig names a VRM model record in the private avatars.json and rigRevisionSha256,
--   when set, its sha256. admit refuses it without the model's likeness consent and appearance approval.
--   width is a fraction of the base width, 0.10 to 0.30. avatarOff names pages (Slides.pages ids) whose whole
--   span hides the overlay, the deck pattern for dense screens; it fades out over fadeS before such a span and
--   back in over fadeS after it. The avatar is on by default for an edition that allows one (NV-8); a job turns
--   it off with avatar None or a segment's avatar False.
-- Slides: named pages on the base clock, each showing the base, a slide picture (by SHA-256 in the private
--   store) or a hold of the base frame at the page's start. layout Full shows a slide over the whole frame.
--   CardLowerLeft (the deck seat's slide card, built here from its description only) shows it as a card in the
--   lower left, cardWidth of the frame wide and marginPx from the edges. A run of adjacent slide pages fades
--   in over fadeS, crossfades in place between pages and fades out over fadeS. Under the card the base frame
--   at the run's end (the next clip's first frame) is held and dims to dimTo of its brightness, lifting again
--   as the card fades out. A Hold page shows no card at full brightness. The avatar keeps its own corner.
-- Music levels (NV-2): the un-ducked bed sits bedBelowVoiceLu (about 20) below the narration's integrated
--   loudness. The sidechain ducks it a further duckDb (6 to 8; refused above 12) under the whole foreground,
--   voice and kept clip sound alike. Fades are 3 s in and 5 s out.
-- Labels.persona: manifest metadata. Required when an avatar is on, and equal to the consent record's persona
--   when a segment's voice has one. No visible label is required in captions or description.txt (KP-15,
--   TIN-7476 comment 4ab7fc27). personaCue (an opening caption cue) and extraNotice (a description.txt line)
--   are optional; when a job sets one, the stages keep it.
-- Delivery: narration is measured at targetLufs integrated and the whole mix is never loudness-normalised.
--   One limiter, in mix. driftLu (at most 0.5) and truePeakDbtp (at most -1.5) are hard gates. upload arms
--   the licence and Content ID gates. voiceOnlyListen names the receipt of a voice-only listen pass, one of
--   the three conditions a client delivery needs before it may carry a bed.
-- defaults.edition is Internal for a simple job (NV-2). defaults.clientEdition is the edition of a client
--   delivery, ClientNarrated (NV-6); a project may pick ClientVoiceOnly instead.
-- Union payloads are records keyed by the constructor's name ({ still = ... }, { atSeconds = ... }), because
--   dhall-to-json drops union tags: the rendered JSON stays unambiguous ({"still": {...}}, "Auto").
-- planLeaves and plan: the Plan point of Edition.check. `bed` is the resolved private record that the job's
--   music names, if any. At Plan, avatar is any avatar block, so a ClientVoiceOnly job that configures an
--   avatar with every segment switched off is still refused. A job has no camera field, so pip is False at
--   Plan; Place reads camera picture-in-picture from an imported deck's stems.
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
      , avatarOff : List Text
      , fadeS : Double
      }

let SlideLayout = < Full | CardLowerLeft >

let Slide = { sha256 : Text }

let PageShow = < Base | Hold | Slide : { slide : Slide } >

let Page = { id : Text, startS : Double, endS : Double, show : PageShow }

let Slides =
      { layout : SlideLayout
      , cardWidth : Double
      , marginPx : Natural
      , fadeS : Double
      , dimTo : Double
      , pages : List Page
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

let Tighten = { enabled : Bool }

let Captions = { soft : Bool, burn : Bool, srt : Bool, vtt : Bool }

let Labels =
      { persona : Optional Text
      , personaCue : Optional Text
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
      , slides : Optional Slides
      , music : Optional Music
      , tighten : Tighten
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
        , avatar = isSome Avatar job.avatar
        , pip = False
        , bed = isSome Music job.music
        , bedCleared = bedCleared job bed
        }

let plan =
      \(job : T) ->
      \(bed : Optional MusicBed.Type) ->
        Edition.check Edition.Point.Plan job.edition (planLeaves job bed)

let personaLabelled =
      \(job : T) -> avatarOn job == False || isSome Text job.labels.persona

let tightenEdits =
      \(job : T) ->
        merge
          { Still = \(_ : { still : Still }) -> False
          , Card = \(_ : { card : Card }) -> False
          , Video = \(_ : { video : Video }) -> False
          , Deck =
              \(d : { deck : Deck }) -> isSome Text d.deck.tightenEditsSha256
          }
          job.base

let tightenAdmitted =
      \(job : T) ->
            job.tighten.enabled
        ||  tightenEdits job == False
        ||  syntheticVoice job == False

let defaults =
      { edition = Edition.Edition.Internal
      , clientEdition = Edition.clientDefault
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
        , avatarOff = [] : List Text
        , fadeS = 0.35
        }
      , slides =
        { layout = SlideLayout.Full
        , cardWidth = 0.42
        , marginPx = 64
        , fadeS = 0.35
        , dimTo = 0.5
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
      , tighten.enabled = False
      , labels =
        { persona = None Text, personaCue = None Text, extraNotice = None Text }
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
    , SlideLayout
    , Slide
    , PageShow
    , Page
    , Slides
    , DuckMode
    , Music
    , Tighten
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
    , tightenEdits
    , tightenAdmitted
    , defaults
    }
