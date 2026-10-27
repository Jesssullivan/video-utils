-- Who a narrated video is for, and what its sources may hold (docs/spec/NARRATED_VIDEO.md, "Editions").
--
-- Internal: synthetic voice, avatar and bed allowed; the default for a simple job until a first listening
-- receipt (NV-2, TIN-7476 comment 9db389dc).
-- OwnContent: the operator's own voice and content; synthetic voice, avatar and bed allowed.
-- ClientVoiceOnly: operator takes only. Refuses synthetic voice, any avatar or other picture-in-picture,
-- and a music bed until the bed is cleared: licence PDF digest recorded, Content ID clear and a
-- voice-only listen pass recorded (NV-2).
--
-- One rule, `check`, runs at three points: Plan (admit, over the job), Place (over the placed stems'
-- manifests) and DeliverCheck (over the labels re-derived from the composed leaves). Each point sees its
-- own Leaves, so a synthetic stem that reaches place under a clean job is still refused there.
let Edition = < Internal | OwnContent | ClientVoiceOnly >

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
        merge { Internal = False, OwnContent = False, ClientVoiceOnly = True } e

let when =
      \(c : Bool) -> \(code : Code) -> if c then [ code ] else [] : List Code

let codes =
      \(e : Edition) ->
      \(l : Leaves) ->
        if    voiceOnly e
        then    when l.syntheticVoice Code.VoiceRefused
              # when (l.avatar || l.pip) Code.PipRefused
              # when (l.bed && l.bedCleared == False) Code.BedRefused
        else  [] : List Code

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
    , check
    , clean
    }
