-- Private character-presentation source handoff. This describes inputs, not permission to render.
-- The client edition remains voice-only/PIP off. A separate internal variant uses approved authored
-- character scripts and provider-neutral audio/avatar files; original client records stay immutable.
let Asset = { path : Text, sha256 : Text }

let ApprovedAsset =
      { path : Text
      , sha256 : Text
      , subjectId : Text
      , scope : Text
      , approvalReference : Text
      , kind : Optional Text
      , scriptSha256 : Optional Text
      }

let Page =
      { id : Text
      , script : Asset
      , targetSeconds : Natural
      , captures : List Asset
      , approvedScript : Optional ApprovedAsset
      , narration : Optional ApprovedAsset
      , avatar : Optional ApprovedAsset
      }

let T =
      { schemaVersion : Natural
      , projectId : Text
      , edition : Text
      , projectRoot : Text
      , source : { repository : Text, commit : Text }
      , clientConfig : Asset
      , expectedPages : Natural
      , pages : List Page
      , assetsRoot : Optional Text
      , sourceFiles : List Asset
      }

in  { Type = T, Asset, ApprovedAsset, Page }
