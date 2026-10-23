-- The local spoken-normalisation table: written forms the engines misread, and what to say instead.
-- xoxd-lexical has no pronunciation lexicon, so this table is narrate's own until an upstream register
-- exists. Normalisation runs after the lexical pass and never changes a number's value.
let Entry =
      { written : Text
      , spoken : Text
      , caseSensitive : Bool
      , wholeWord : Bool
      , note : Optional Text
      }

let T = { id : Text, language : Text, entries : List Entry }

in  { Type = T, Entry }
