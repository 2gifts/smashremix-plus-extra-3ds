/* Japanese Samus from the pinned Remix reference ROM. Its independent
 * action table carries the regional jab, up smash and Screw Attack scripts. */
#include <ft/fighter.h>
#include <string.h>
#include "fighter_registry.h"
#include "native_remix_roster.h"

extern u32 portRelocRegisterPointer(void *);
extern void port_log(const char *, ...);
#include "jsamus_data.inc"

static FTData jsamus_data;
static void *jsamus_files[9];
static s32 jsamus_particle;

int nativeRemixJSamusIsAnimation(unsigned fid) {
    if (!fid) return 0;
    for (unsigned i = 0; i < ARRAY_COUNT(remix_jsamus_main_motions); i++)
        if (remix_jsamus_main_motions[i].anim_file_id == fid &&
            !(remix_jsamus_main_motions[i].anim_desc.word & (FTANIM_FLAG_ANIMJOINT | FTANIM_FLAG_SHIELDPOSE))) return 1;
    for (unsigned i = 0; i < ARRAY_COUNT(remix_jsamus_menu_motions); i++)
        if (remix_jsamus_menu_motions[i].anim_file_id == fid &&
            !(remix_jsamus_menu_motions[i].anim_desc.word & (FTANIM_FLAG_ANIMJOINT | FTANIM_FLAG_SHIELDPOSE))) return 1;
    return 0;
}

void nativeRemixJSamusInit(void) {
    FighterDescriptor desc = *port_fighter_descriptor(nFTKindSamus);
    jsamus_data = *desc.ft_data;
    memcpy(&jsamus_data.file_main_id, remix_jsamus_files, sizeof(remix_jsamus_files));
    jsamus_data.o_attributes = REMIX_JSAMUS_ATTRIBUTE_OFFSET;
    jsamus_data.mainmotion = (FTMotionDescArray *)remix_jsamus_main_motions;
    jsamus_data.mainmotion_array_count = ARRAY_COUNT(remix_jsamus_main_motions);
    jsamus_data.submotion = (FTMotionDescArray *)remix_jsamus_menu_motions;
    jsamus_data.submotion_array_count = &remix_jsamus_menu_count;
    jsamus_data.p_file_main = &jsamus_files[0];
    jsamus_data.p_file_mainmotion = &jsamus_files[1];
    jsamus_data.p_file_submotion = &jsamus_files[2];
    jsamus_data.p_file_model = &jsamus_files[3];
    jsamus_data.p_file_shieldpose = &jsamus_files[4];
    jsamus_data.p_file_special1 = &jsamus_files[5];
    jsamus_data.p_file_special2 = &jsamus_files[6];
    jsamus_data.p_file_special3 = &jsamus_files[7];
    jsamus_data.p_file_special4 = &jsamus_files[8];
    jsamus_data.p_particle = &jsamus_particle;
    desc.ft_data = &jsamus_data;
    remix_jsamus_relocate_scripts();
    port_fighter_register(NATIVE_REMIX_JSAMUS_KIND, &desc);
    port_log("REMIX PROBE: native J Samus registered at fkind %u\n", NATIVE_REMIX_JSAMUS_KIND);
}
