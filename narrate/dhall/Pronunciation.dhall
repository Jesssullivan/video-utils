-- The local spoken-normalisation table: written forms the engines misread, and what to say instead.
-- The pinned xoxd-lexical narration table runs first; this local table is an explicit overlay.
-- Normalisation runs after the written accuracy check and never changes a number's value.
let Entry =
      { written : Text
      , spoken : Text
      , caseSensitive : Bool
      , wholeWord : Bool
      , note : Optional Text
      }

let T = { id : Text, language : Text, entries : List Entry }

in  { Type = T, Entry }
