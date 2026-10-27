-- Who a narrated video is for, and what its sources may hold (docs/spec/NARRATED_VIDEO.md, "Editions").
--
-- Internal: synthetic voice, avatar and bed allowed; the default for a simple job until a first listening
-- receipt (NV-2, TIN-7476 comment 9db389dc).
-- OwnContent: the operator's own voice and content; synthetic voice, avatar and bed allowed.
-- ClientVoiceOnly: operator takes only. Refuses synthetic voice, any avatar or other picture-in-picture,
-- and an uncleared music bed.
-- ClientNarrated: a client delivery that carries the synthetic narrator and the kitpip avatar (the deck
-- project's ruling 59(d), TIN-7476 comment e427ecfc). Refuses camera picture-in-picture and an uncleared
-- music bed.
--
-- Every client edition gates the bed: it is cleared only when its licence PDF digest is recorded, its
-- Content ID result is clear and a voice-only listen pass is recorded (NV-2).
--
-- Leaves: avatar is a kitpip overlay; pip is any other picture-in-picture, such as a camera of the
-- operator. One rule, `check`, runs at three points: Plan (admit, over the job), Place (over the placed
-- stems' manifests) and DeliverCheck (over the labels re-derived from the composed leaves). Each point sees
-- its own Leaves, so a synthetic stem that reaches place under a clean job is still refused there.
let Edition = < Internal | OwnContent | ClientVoiceOnly | ClientNarrated >

let Point = < Plan | Place | DeliverCheck >

let Code = < VoiceRefused | PipRefused | BedRefused >

let Leaves =
      { syntheticVoice : Bool
      , avatar : Bool
      , pip : Bool
      , bed : Bool
      , bedCleared : Bool
      }

let Verdict = < Admitted | Refused : { point : Point, codes : List Code } >

let voiceOnly =
      \(e : Edition) ->
        merge
          { Internal = False
          , OwnContent = False
          , ClientVoiceOnly = True
          , ClientNarrated = False
          }
          e

let client =
      \(e : Edition) ->
        merge
          { Internal = False
          , OwnContent = False
          , ClientVoiceOnly = True
          , ClientNarrated = True
          }
          e

let when =
      \(c : Bool) -> \(code : Code) -> if c then [ code ] else [] : List Code

let codes =
      \(e : Edition) ->
      \(l : Leaves) ->
          ( if    voiceOnly e
            then    when l.syntheticVoice Code.VoiceRefused
                  # when (l.avatar || l.pip) Code.PipRefused
            else  when (client e && l.pip) Code.PipRefused
          )
        # when (client e && l.bed && l.bedCleared == False) Code.BedRefused

let check =
      \(p : Point) ->
      \(e : Edition) ->
      \(l : Leaves) ->
        let found = codes e l

        in  if    Natural/isZero (List/length Code found)
            then  Verdict.Admitted
            else  Verdict.Refused { point = p, codes = found }

let clean
    : Leaves
    = { syntheticVoice = False
      , avatar = False
      , pip = False
      , bed = False
      , bedCleared = False
      }

in  { Type = Edition
    , Edition
    , Point
    , Code
    , Leaves
    , Verdict
    , voiceOnly
    , client
    , check
    , clean
    }
