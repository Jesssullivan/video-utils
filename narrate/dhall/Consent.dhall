-- A consent record. Every voice names one; a voice without a matching, unrevoked record is refused.
-- The evidence itself (a signed statement or recording) is hash-bound and lives outside git.
-- persona (NV-1, TIN-7476 comment 9db389dc): the AI-persona label a persona voice's media must carry. The real
-- value lives only in the private record; a narrated video's Labels.persona must equal it.
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
      , persona : Optional Text
      }

in  { Type = T, Scope, default.persona = None Text }
