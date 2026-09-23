#ifndef NATIVE_REMIX_STAGES_H
#define NATIVE_REMIX_STAGES_H

#include <stdint.h>

/* Data comes from the final assembled Remix +EXTRA ROM at local build time. */
typedef struct NativeRemixStageRecord {
    uint32_t header_file_id;
    uint32_t header_offset;
    uint16_t setup_kind; /* 0: no hazards, 1..9: original setup, 255: unported */
    uint8_t stage_class;
    uint16_t default_music_plus_one;
    int16_t alternate_music[4];
} NativeRemixStageRecord;

extern const NativeRemixStageRecord native_remix_stages[];
extern const unsigned native_remix_stage_count;
const NativeRemixStageRecord *nativeRemixStageGet(unsigned kind);

#endif
