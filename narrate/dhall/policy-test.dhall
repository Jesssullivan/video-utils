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
      , files = [] : List Engine.File
      , licence = "probe"
      , licenceNotice = None Text
      , vramGiB = None Double
      , sampleRateHz = Some 24000
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

let hostedBackendBehindLocalProfile =
        assert
      :     Engine.mayRunConfidential
              (     base
                //  { profile = Engine.Profile.GpuDirect
                    , backend = Engine.Backend.Hosted
                    , hosted = False
                    }
              )
        ===  False

let hostedBackendIsHosted =
        assert
      : Engine.isHosted (base // { backend = Engine.Backend.Hosted }) === True

let hostedFlagAloneIsHosted =
      assert : Engine.isHosted (base // { hosted = True }) === True

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

let rentedBackendBehindMacProfile =
        assert
      :     Engine.mayRunConfidential
              (     base
                //  { profile = Engine.Profile.MacMlx
                    , backend = Engine.Backend.RentedOpen
                    , estateControlled = False
                    }
              )
        ===  False

let rentedBackendIsRented =
        assert
      :     Engine.isRented
              (     base
                //  { profile = Engine.Profile.MacMlx
                    , backend = Engine.Backend.RentedOpen
                    }
              )
        ===  True

let rentedEstateFlagged =
        assert
      :     Engine.mayRunConfidential
              (     base
                //  { profile = Engine.Profile.RentedOpen
                    , backend = Engine.Backend.RentedOpen
                    }
              )
        ===  True

let mismatchedProfileIsInconsistent =
        assert
      :     Engine.consistent (base // { backend = Engine.Backend.MlxAudio })
        ===  False

let hostedFlagOnLocalProfileIsInconsistent =
      assert : Engine.consistent (base // { hosted = True }) === False

let macMlxConsistent =
        assert
      :     Engine.consistent
              (     base
                //  { profile = Engine.Profile.MacMlx
                    , backend = Engine.Backend.MlxAudio
                    }
              )
        ===  True

let hostedConsistent =
        assert
      :     Engine.consistent
              (     base
                //  { profile = Engine.Profile.Hosted
                    , backend = Engine.Backend.Hosted
                    , hosted = True
                    }
              )
        ===  True

let audioCppBatchDirectConsistent =
        assert
      :     Engine.consistent
              (     base
                //  { endpoint = "audiocpp://voxcpm2"
                    , backend = Engine.Backend.AudioCppBatch
                    }
              )
        ===  True

let audioCppBatchDirectMayRunConfidential =
        assert
      :     Engine.mayRunConfidential
              (base // { backend = Engine.Backend.AudioCppBatch })
        ===  True

let audioCppBatchBehindSwitchIsInconsistent =
        assert
      :     Engine.consistent
              (     base
                //  { profile = Engine.Profile.GpuSwitch
                    , backend = Engine.Backend.AudioCppBatch
                    }
              )
        ===  False

let audioCppBatchBehindMacIsInconsistent =
        assert
      :     Engine.consistent
              (     base
                //  { profile = Engine.Profile.MacMlx
                    , backend = Engine.Backend.AudioCppBatch
                    }
              )
        ===  False

in  True
