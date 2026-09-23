/* Japanese Yoshi from the pinned Remix reference ROM. Its independently
 * backed motion data includes the regional up tilt, down tilt, and down smash scripts. */
#include <ft/fighter.h>
#include <string.h>
#include "fighter_registry.h"
#include "native_remix_roster.h"

extern u32 portRelocRegisterPointer(void *);
extern void port_log(const char *, ...);
#include "jyoshi_data.inc"

static FTData jyoshi_data;
static void *jyoshi_files[9];
static s32 jyoshi_particle;

int nativeRemixJYoshiIsAnimation(unsigned fid) {
    if (!fid) return 0;
    for (unsigned i = 0; i < ARRAY_COUNT(remix_jyoshi_main_motions); i++)
        if (remix_jyoshi_main_motions[i].anim_file_id == fid &&
            !(remix_jyoshi_main_motions[i].anim_desc.word & (FTANIM_FLAG_ANIMJOINT | FTANIM_FLAG_SHIELDPOSE))) return 1;
    for (unsigned i = 0; i < ARRAY_COUNT(remix_jyoshi_menu_motions); i++)
        if (remix_jyoshi_menu_motions[i].anim_file_id == fid &&
            !(remix_jyoshi_menu_motions[i].anim_desc.word & (FTANIM_FLAG_ANIMJOINT | FTANIM_FLAG_SHIELDPOSE))) return 1;
    return 0;
}

void nativeRemixJYoshiInit(void) {
    FighterDescriptor desc = *port_fighter_descriptor(nFTKindYoshi);
    jyoshi_data = *desc.ft_data;
    memcpy(&jyoshi_data.file_main_id, remix_jyoshi_files, sizeof(remix_jyoshi_files));
    jyoshi_data.o_attributes = REMIX_JYOSHI_ATTRIBUTE_OFFSET;
    jyoshi_data.mainmotion = (FTMotionDescArray *)remix_jyoshi_main_motions;
    jyoshi_data.mainmotion_array_count = ARRAY_COUNT(remix_jyoshi_main_motions);
    jyoshi_data.submotion = (FTMotionDescArray *)remix_jyoshi_menu_motions;
    jyoshi_data.submotion_array_count = &remix_jyoshi_menu_count;
    jyoshi_data.p_file_main = &jyoshi_files[0];
    jyoshi_data.p_file_mainmotion = &jyoshi_files[1];
    jyoshi_data.p_file_submotion = &jyoshi_files[2];
    jyoshi_data.p_file_model = &jyoshi_files[3];
    jyoshi_data.p_file_shieldpose = &jyoshi_files[4];
    jyoshi_data.p_file_special1 = &jyoshi_files[5];
    jyoshi_data.p_file_special2 = &jyoshi_files[6];
    jyoshi_data.p_file_special3 = &jyoshi_files[7];
    jyoshi_data.p_file_special4 = &jyoshi_files[8];
    jyoshi_data.p_particle = &jyoshi_particle;
    desc.ft_data = &jyoshi_data;
    remix_jyoshi_relocate_scripts();
    port_fighter_register(NATIVE_REMIX_JYOSHI_KIND, &desc);
    port_log("REMIX PROBE: native J Yoshi registered at fkind %u\n", NATIVE_REMIX_JYOSHI_KIND);
}
