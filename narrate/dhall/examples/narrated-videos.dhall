-- Fixture narrated-video jobs (docs/spec/NARRATED_VIDEO.md), bound to synthetic inputs only: the fixture
-- narrate job (examples/jobs.dhall), the fixture bed (examples/music-beds.dhall) and three generated deck
-- placeholders and one generated tighten-edits placeholder (narrate/dhall/check.py). Real jobs live in the
-- private store.
--
-- nv-fixture-card: the simple default. Internal edition, a colour card, one segment, the fixture bed, no
-- avatar and no caption or description label (KP-15). nv-fixture-avatar: the same with a kitpip avatar, so
-- the persona label is required.
-- nv-fixture-client-deck: ClientVoiceOnly. A deck of operator takes imported by digest, no narrate segment,
-- no avatar and no bed.
-- nv-fixture-client-narrated: ClientNarrated (deck ruling 59(d)). A tightened deck with tighten enabled as a
-- per-project override, one narrate segment, a kitpip avatar with its persona label, and no bed.
-- nv-fixture-slides: the avatar job with two generated slide pictures as a lower-left card, a base page and a
-- 0.4 s hold at the end. The avatar is off for the second slide page.
let NarratedVideo = ../NarratedVideo.dhall

let Edition = ../Edition.dhall

let d = NarratedVideo.defaults

let card =
      NarratedVideo.Base.Card
        { card =
          { colour = "#101820", size = d.size, fps = d.fps, tailS = d.tailS }
        }

let segment =
      { id = "seg-1"
      , narrateJob = "job-fixture-fake"
      , scriptSha256 =
          "93f7f4183b4b6ccec0c3ef2c83cca16dcb0ec4a929d55941193ab84f4f355d3a"
      , anchor = NarratedVideo.Anchor.Auto
      , avatar = True
      }

let music = d.music // { bed = "bed-fixture-emaj" }

let simple
    : NarratedVideo.Type
    = { id = "nv-fixture-card"
      , edition = d.edition
      , base = card
      , segments = [ segment ]
      , avatar = None NarratedVideo.Avatar
      , slides = None NarratedVideo.Slides
      , music = Some music
      , tighten = d.tighten
      , captions = d.captions
      , labels = d.labels
      , delivery = d.delivery
      }

let withAvatar
    : NarratedVideo.Type
    =     simple
      //  { id = "nv-fixture-avatar"
          , avatar = Some d.avatar
          , labels = d.labels // { persona = Some "fixture-persona" }
          }

let deck =
      { producer = "fixture-deck-assembler"
      , videoSha256 =
          "84c0b8d31bfe1b39386a634f91ed79b6210b6da497685e8ce4ccaaf97e436b9f"
      , timelineSha256 =
          "767e6bb830e8f2a4b89cda71bd9ff152573e108761393bd7fab11871f9e420a9"
      , stemsSha256 =
          "ba12eea14e9c325423bd4e9ec9e2db79452f82e14518d52fee7632a01470b626"
      , tightenEditsSha256 = None Text
      }

let clientDeck
    : NarratedVideo.Type
    = { id = "nv-fixture-client-deck"
      , edition = Edition.Edition.ClientVoiceOnly
      , base = NarratedVideo.Base.Deck { deck }
      , segments = [] : List NarratedVideo.Segment
      , avatar = None NarratedVideo.Avatar
      , slides = None NarratedVideo.Slides
      , music = None NarratedVideo.Music
      , tighten = d.tighten
      , captions = d.captions
      , labels = d.labels
      , delivery = d.delivery
      }

let clientNarrated
    : NarratedVideo.Type
    =     withAvatar
      //  { id = "nv-fixture-client-narrated"
          , edition = Edition.Edition.ClientNarrated
          , base =
              NarratedVideo.Base.Deck
                { deck =
                        deck
                    //  { tightenEditsSha256 = Some
                            "00954c81b66e26d5077c9853b7087ea4545f489b7823b237c08bcc9eb0ca852f"
                        }
                }
          , music = None NarratedVideo.Music
          , tighten.enabled = True
          }

let slide =
      \(id : Text) ->
      \(startS : Double) ->
      \(endS : Double) ->
      \(sha256 : Text) ->
        { id
        , startS
        , endS
        , show = NarratedVideo.PageShow.Slide { slide.sha256 = sha256 }
        }

let withSlides
    : NarratedVideo.Type
    =     withAvatar
      //  { id = "nv-fixture-slides"
          , avatar = Some (d.avatar // { avatarOff = [ "slide-b" ] })
          , slides = Some
              (     d.slides
                //  { layout = NarratedVideo.SlideLayout.CardLowerLeft
                    , pages =
                      [ slide
                          "slide-a"
                          0.0
                          2.0
                          "3b3071d75a77285d84f1427864df16d6aba49d5d1015e33be8ef024d66383a09"
                      , slide
                          "slide-b"
                          2.0
                          4.0
                          "f428bf2bc4488211d76cb234074cea1da1ffddef19122426bc83e2719f7db86e"
                      , { id = "body"
                        , startS = 4.0
                        , endS = 5.0
                        , show = NarratedVideo.PageShow.Base
                        }
                      , { id = "end"
                        , startS = 5.0
                        , endS = 5.4
                        , show = NarratedVideo.PageShow.Hold
                        }
                      ]
                    }
              )
          }

in    [ simple, withAvatar, clientDeck, clientNarrated, withSlides ]
    : List NarratedVideo.Type
