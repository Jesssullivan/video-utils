#import <AudioToolbox/AudioToolbox.h>
#import <Foundation/Foundation.h>

NS_ASSUME_NONNULL_BEGIN

/// Internal native kernel; configuration/lifecycle calls require stopped rendering.
@interface VUGainKernel : NSObject
- (BOOL)prepareWithMaximumFrames:(uint32_t)frames channels:(uint32_t)channels;
- (void)releaseResources;
- (BOOL)setLinearGain:(float)gain;
@property(nonatomic, readonly) AUInternalRenderBlock renderBlock;
@end

NS_ASSUME_NONNULL_END
