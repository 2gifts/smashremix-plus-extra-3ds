#include "native_remix_stages.h"
#include <stddef.h>

#include "native_stage_tables.inc"

const NativeRemixStageRecord *nativeRemixStageGet(unsigned kind)
{
    if (kind >= native_remix_stage_count || native_remix_stages[kind].header_file_id == 0)
    {
        return NULL;
    }
    return &native_remix_stages[kind];
}
