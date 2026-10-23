-- A synthesis engine: one model on one serving path (docs/spec/NARRATE.md, "Engine profiles").
-- Real engine instances carry private endpoints and live outside git; this repository holds the type,
-- the fake test engine and the policy below.
let Backend =
      < VulkanAudioCpp
      | QwenTtsCpp
      | LlamaTts
      | MlxAudio
      | RentedOpen
      | Hosted
      | Fake
      >

let Profile = < GpuSwitch | GpuDirect | MacMlx | RentedOpen | Hosted | Fake >

let T =
      { id : Text
      , profile : Profile
      , backend : Backend
      , endpoint : Text
      , model : Text
      , hfRepo : Optional Text
      , hfRevision : Optional Text
      , sha256 : List Text
      , licence : Text
      , licenceNotice : Optional Text
      , vramGiB : Optional Double
      , sampleRateHz : Natural
      , hosted : Bool
      , estateControlled : Bool
      , confidentialAllowed : Bool
      }

let isRented =
      \(e : T) ->
        merge
          { GpuSwitch = False
          , GpuDirect = False
          , MacMlx = False
          , RentedOpen = True
          , Hosted = False
          , Fake = False
          }
          e.profile

let isHostedProfile =
      \(e : T) ->
        merge
          { GpuSwitch = False
          , GpuDirect = False
          , MacMlx = False
          , RentedOpen = False
          , Hosted = True
          , Fake = False
          }
          e.profile

let mayRunConfidential =
      \(e : T) ->
            (e.hosted || isHostedProfile e) == False
        &&  e.confidentialAllowed
        &&  (isRented e == False || e.estateControlled)

in  { Type = T
    , Backend
    , Profile
    , isRented
    , isHostedProfile
    , mayRunConfidential
    }
