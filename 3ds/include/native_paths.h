#pragma once
/* Separate from Smash 64's save/config/report directory. Remix's expanded
 * save layout must never be interpreted as a vanilla save, or vice versa. */
#ifdef SSB_REMIX_PROBE
#define NATIVE_SD_DIRECTORY "sdmc:/3ds/ssb64-remix-falco-test"
#else
#define NATIVE_SD_DIRECTORY "sdmc:/3ds/ssb64-remix-extra"
#endif
