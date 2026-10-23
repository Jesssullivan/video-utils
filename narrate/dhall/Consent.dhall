-- A consent record. Every voice names one; a voice without a matching, unrevoked record is refused.
-- The evidence itself (a signed statement or recording) is hash-bound and lives outside git.
let Scope = < OwnContent | ClientDisclosed >

let T =
      { id : Text
      , speaker : Text
      , grantedAt : Text
      , grantedBy : Text
      , scopes : List Scope
      , hostedAllowed : Bool
      , revocable : Bool
      , revokedAt : Optional Text
      , evidenceSha256 : Text
      , syntheticLabelRequired : Bool
      }

in  { Type = T, Scope }
