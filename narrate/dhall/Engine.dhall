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

let File = { path : Text, sha256 : Text }

let T =
      { id : Text
      , profile : Profile
      , backend : Backend
      , endpoint : Text
      , model : Text
      , hfRepo : Optional Text
      , hfRevision : Optional Text
      , files : List File
      , licence : Text
      , licenceNotice : Optional Text
      , vramGiB : Optional Double
      , sampleRateHz : Optional Natural
      , hosted : Bool
      , estateControlled : Bool
      , confidentialAllowed : Bool
      }

let profileIsRented =
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

let backendIsRented =
      \(e : T) ->
        merge
          { VulkanAudioCpp = False
          , QwenTtsCpp = False
          , LlamaTts = False
          , MlxAudio = False
          , RentedOpen = True
          , Hosted = False
          , Fake = False
          }
          e.backend

let profileIsHosted =
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

let backendIsHosted =
      \(e : T) ->
        merge
          { VulkanAudioCpp = False
          , QwenTtsCpp = False
          , LlamaTts = False
          , MlxAudio = False
          , RentedOpen = False
          , Hosted = True
          , Fake = False
          }
          e.backend

let isRented = \(e : T) -> profileIsRented e || backendIsRented e

let isHosted = \(e : T) -> e.hosted || profileIsHosted e || backendIsHosted e

let backendFitsProfile =
      \(e : T) ->
        let local =
              merge
                { VulkanAudioCpp = True
                , QwenTtsCpp = True
                , LlamaTts = True
                , MlxAudio = False
                , RentedOpen = False
                , Hosted = False
                , Fake = False
                }
                e.backend

        let mlx =
              merge
                { VulkanAudioCpp = False
                , QwenTtsCpp = False
                , LlamaTts = False
                , MlxAudio = True
                , RentedOpen = False
                , Hosted = False
                , Fake = False
                }
                e.backend

        let fake =
              merge
                { VulkanAudioCpp = False
                , QwenTtsCpp = False
                , LlamaTts = False
                , MlxAudio = False
                , RentedOpen = False
                , Hosted = False
                , Fake = True
                }
                e.backend

        in  merge
              { GpuSwitch = local
              , GpuDirect = local
              , MacMlx = mlx
              , RentedOpen = backendIsRented e
              , Hosted = backendIsHosted e
              , Fake = fake
              }
              e.profile

let consistent =
      \(e : T) -> backendFitsProfile e && e.hosted == profileIsHosted e

let mayRunConfidential =
      \(e : T) ->
            consistent e
        &&  isHosted e == False
        &&  e.confidentialAllowed
        &&  (isRented e == False || e.estateControlled)

in  { Type = T
    , File
    , Backend
    , Profile
    , isRented
    , isHosted
    , consistent
    , mayRunConfidential
    }
