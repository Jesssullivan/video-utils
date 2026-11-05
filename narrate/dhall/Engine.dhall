-- A synthesis engine: one model on one serving path (docs/spec/NARRATE.md, "Engine profiles").
-- Real engine instances carry private endpoints and live outside git; this repository holds the type,
-- the fake test engine and the policy below.
--
-- AudioCppBatch is audio.cpp's audiocpp_cli run out of process as a request batch (it has no server at the
-- pinned commit): `narrate plan` writes the requests, the GPU window runs them, and `narrate render
-- --prerendered` reads the takes by request id (narrate/prerender.py). Its endpoint is audiocpp://<family>,
-- and its files pin the binary and the weights by sha256. GpuDirect admits it for an attended window on the local
-- card. RentedAudioCppBatch is the same batch on a rented or offsite GPU, under the RentedOpen profile. A separate
-- backend keeps the location in two fields, so changing the profile or the backend alone fails `consistent`.
--
-- isOffsite is a hosted or rented engine, and the voice's consent record must allow it (hostedAllowed, TIN-7125
-- af4ceb3b). mayRunConfidential is a report-only label (TIN-7125 f98fd1ac): no refusal reads it, and it and the fields
-- estateControlled and confidentialAllowed stay until the TIN-7994 audit decides what comes back.
let Backend =
      < VulkanAudioCpp
      | AudioCppBatch
      | RentedAudioCppBatch
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
          , AudioCppBatch = False
          , RentedAudioCppBatch = True
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
          , AudioCppBatch = False
          , RentedAudioCppBatch = False
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
                , AudioCppBatch = False
                , RentedAudioCppBatch = False
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
                , AudioCppBatch = False
                , RentedAudioCppBatch = False
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
                , AudioCppBatch = False
                , RentedAudioCppBatch = False
                , QwenTtsCpp = False
                , LlamaTts = False
                , MlxAudio = False
                , RentedOpen = False
                , Hosted = False
                , Fake = True
                }
                e.backend

        let batch =
              merge
                { VulkanAudioCpp = False
                , AudioCppBatch = True
                , RentedAudioCppBatch = False
                , QwenTtsCpp = False
                , LlamaTts = False
                , MlxAudio = False
                , RentedOpen = False
                , Hosted = False
                , Fake = False
                }
                e.backend

        in  merge
              { GpuSwitch = local
              , GpuDirect = local || batch
              , MacMlx = mlx
              , RentedOpen = backendIsRented e
              , Hosted = backendIsHosted e
              , Fake = fake
              }
              e.profile

let consistent =
      \(e : T) -> backendFitsProfile e && e.hosted == profileIsHosted e

let isOffsite = \(e : T) -> isHosted e || isRented e

let mayRunConfidential = consistent

in  { Type = T
    , File
    , Backend
    , Profile
    , isRented
    , isHosted
    , isOffsite
    , consistent
    , mayRunConfidential
    }
