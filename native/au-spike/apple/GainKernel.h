#import <AudioToolbox/AudioToolbox.h>
#import <Foundation/Foundation.h>

NS_ASSUME_NONNULL_BEGIN

/// Internal native kernel; configuration/lifecycle calls require stopped rendering.
@interface VUGainKernel : NSObject
- (BOOL)prepareWithMaximumFrames:(uint32_t)frames channels:(uint32_t)channels;
- (void)releaseResources;
- (BOOL)setLinearGain:(float)gain;
@property(nonatomic, readonly) AUInternalRenderBlock renderBlock;
@property(nonatomic, readonly) AUImplementorValueObserver gainValueObserver;
@property(nonatomic, readonly) AUImplementorValueProvider gainValueProvider;
@property(nonatomic, readonly) uint64_t stateToken;
/// Only read on the stopped lifecycle owner; UINT64_MAX denotes active/unavailable.
@property(nonatomic, readonly) uint64_t stateRevision;
- (nullable NSData *)copyPrivateStateForToken:(uint64_t)token NS_SWIFT_NAME(copyPrivateState(forToken:));
/// Non-render operation. Zero succeeds; nonzero is vus::Status.
- (int32_t)restorePrivateState:(NSData *)data expectedRevision:(uint64_t)revision expectedToken:(uint64_t)token;
@end

NS_ASSUME_NONNULL_END
