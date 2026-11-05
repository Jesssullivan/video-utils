-- Synthetic planner input only. No actual client, voice, avatar or private path is included.
let Presentation = ../Presentation.dhall

let empty = "0000000000000000000000000000000000000000000000000000000000000000"

let source = { path = "video.json", sha256 = empty }

in    { schemaVersion = 1
      , projectId = "fixture-private"
      , edition = "internal-cade-pip"
      , projectRoot = "/fixture/project"
      , source =
        { repository = "example/private"
        , commit = "0000000000000000000000000000000000000000"
        }
      , clientConfig = source
      , expectedPages = 1
      , pages =
        [ { id = "open"
          , script = { path = "manuscript/01-open.md", sha256 = empty }
          , targetSeconds = 55
          , captures = [] : List Presentation.Asset
          , approvedScript = None Presentation.ApprovedAsset
          , narration = None Presentation.ApprovedAsset
          , avatar = None Presentation.ApprovedAsset
          }
        ]
      , assetsRoot = None Text
      , sourceFiles = [ source ]
      }
    : Presentation.Type
