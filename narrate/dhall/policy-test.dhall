-- Type-level tests of the confidentiality rule. `dhall type` fails if any assertion is false.
let Engine = ./Engine.dhall

let base
    : Engine.Type
    = { id = "policy-probe"
      , profile = Engine.Profile.GpuDirect
      , backend = Engine.Backend.VulkanAudioCpp
      , endpoint = "fake://probe"
      , model = "probe"
      , hfRepo = None Text
      , hfRevision = None Text
      , sha256 = [] : List Text
      , licence = "probe"
      , licenceNotice = None Text
      , vramGiB = None Double
      , sampleRateHz = 24000
      , hosted = False
      , estateControlled = True
      , confidentialAllowed = True
      }

let localFlagged = assert : Engine.mayRunConfidential base === True

let localUnflagged =
        assert
      :     Engine.mayRunConfidential (base // { confidentialAllowed = False })
        ===  False

let hostedNeverEvenIfFlagged =
        assert
      :     Engine.mayRunConfidential
              (     base
                //  { profile = Engine.Profile.Hosted
                    , backend = Engine.Backend.Hosted
                    , hosted = True
                    }
              )
        ===  False

let hostedProfileWithoutFlag =
        assert
      :     Engine.mayRunConfidential
              (base // { profile = Engine.Profile.Hosted })
        ===  False

let rentedNotEstate =
        assert
      :     Engine.mayRunConfidential
              (     base
                //  { profile = Engine.Profile.RentedOpen
                    , backend = Engine.Backend.RentedOpen
                    , estateControlled = False
                    }
              )
        ===  False

let rentedEstateFlagged =
        assert
      :     Engine.mayRunConfidential
              (     base
                //  { profile = Engine.Profile.RentedOpen
                    , backend = Engine.Backend.RentedOpen
                    }
              )
        ===  True

in  True
