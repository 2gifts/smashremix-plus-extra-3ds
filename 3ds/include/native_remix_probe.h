#ifndef NATIVE_REMIX_PROBE_H
#define NATIVE_REMIX_PROBE_H
/* Integration fixture, compiled only with SSB_REMIX_PROBE. */
void nativeRemixProbeInit(void);
void nativeRemixProbeCommand(GObj *, FTStruct *, FTMotionScript *);
void nativeRemixProbeSeekCommand(GObj *, FTStruct *, FTMotionScript *);
void nativeRemixProbeReset(FTStruct *);
float nativeRemixProbeTranslation(FTStruct *);
void nativeRemixProbeHitboxReset(unsigned player, unsigned slot);
void nativeRemixProbeDamageDirection(FTStruct *, FTStruct *, FTAttackColl *);
unsigned nativeRemixProbeHitFgm(FTStruct *, FTAttackColl *);
unsigned nativeRemixProbeEnvColor(FTStruct *);
#endif
