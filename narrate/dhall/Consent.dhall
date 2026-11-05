-- A consent record. Every voice names one; a voice without a matching, unrevoked record is refused.
-- The evidence itself (a signed statement or recording) is hash-bound and lives outside git.
-- persona (NV-1, TIN-7476 comment 9db389dc): the AI-persona label a persona voice's media must carry. The real
-- value lives only in the private record; a narrated video's Labels.persona must equal it.
-- Likeness (SP-R13, a draft for the VRM offline renderer): the subject grants an avatar likeness. A VRM model
-- record in the private avatars.json names such a consent by id (likenessConsent.id), and narrate/video/vrm.py
-- resolves it in this table; grantedBy must be "Operator". It never grants a voice: a voice or job scope of
-- Likeness refuses consent_scope.
let Scope = < OwnContent | ClientDisclosed | Likeness >

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
