-- A small example table. Entries say how to read a written form; none changes a number's value.
let Pronunciation = ../Pronunciation.dhall

in    { id = "narrate-en-example"
      , language = "en"
      , entries =
        [ { written = "LUFS"
          , spoken = "loudness units relative to full scale"
          , caseSensitive = True
          , wholeWord = True
          , note = Some
              "Spoken in full on first use only; the chunker does not track first use yet."
          }
        , { written = "MCP"
          , spoken = "M C P"
          , caseSensitive = True
          , wholeWord = True
          , note = None Text
          }
        , { written = "8%"
          , spoken = "8 percent"
          , caseSensitive = True
          , wholeWord = False
          , note = Some "The digit stays a digit; the engine reads it."
          }
        ]
      }
    : Pronunciation.Type
