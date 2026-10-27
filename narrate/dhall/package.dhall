-- narrate's typed configuration. Render instances with dhall-to-json; Python reads the JSON.
{ Engine = ./Engine.dhall
, Voice = ./Voice.dhall
, Consent = ./Consent.dhall
, Job = ./Job.dhall
, Pronunciation = ./Pronunciation.dhall
, Edition = ./Edition.dhall
, MusicBed = ./MusicBed.dhall
, NarratedVideo = ./NarratedVideo.dhall
}
