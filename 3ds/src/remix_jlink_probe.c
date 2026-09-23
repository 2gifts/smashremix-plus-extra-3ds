/* Japanese Link from the pinned Remix reference ROM. Its independently
 * backed motion data includes the regional tilt, smash, and aerial scripts. */
#include <ft/fighter.h>
#include <string.h>
#include "fighter_registry.h"
#include "native_remix_roster.h"

extern u32 portRelocRegisterPointer(void *);
extern void port_log(const char *, ...);
#include "jlink_data.inc"

static FTData jlink_data;
static void *jlink_files[9];
static s32 jlink_particle;

int nativeRemixJLinkIsAnimation(unsigned fid) {
    if (!fid) return 0;
    for (unsigned i = 0; i < ARRAY_COUNT(remix_jlink_main_motions); i++)
        if (remix_jlink_main_motions[i].anim_file_id == fid &&
            !(remix_jlink_main_motions[i].anim_desc.word & (FTANIM_FLAG_ANIMJOINT | FTANIM_FLAG_SHIELDPOSE))) return 1;
    for (unsigned i = 0; i < ARRAY_COUNT(remix_jlink_menu_motions); i++)
        if (remix_jlink_menu_motions[i].anim_file_id == fid &&
            !(remix_jlink_menu_motions[i].anim_desc.word & (FTANIM_FLAG_ANIMJOINT | FTANIM_FLAG_SHIELDPOSE))) return 1;
    return 0;
}

void nativeRemixJLinkInit(void) {
    FighterDescriptor desc = *port_fighter_descriptor(nFTKindLink);
    jlink_data = *desc.ft_data;
    memcpy(&jlink_data.file_main_id, remix_jlink_files, sizeof(remix_jlink_files));
    jlink_data.o_attributes = REMIX_JLINK_ATTRIBUTE_OFFSET;
    jlink_data.mainmotion = (FTMotionDescArray *)remix_jlink_main_motions;
    jlink_data.mainmotion_array_count = ARRAY_COUNT(remix_jlink_main_motions);
    jlink_data.submotion = (FTMotionDescArray *)remix_jlink_menu_motions;
    jlink_data.submotion_array_count = &remix_jlink_menu_count;
    jlink_data.p_file_main = &jlink_files[0];
    jlink_data.p_file_mainmotion = &jlink_files[1];
    jlink_data.p_file_submotion = &jlink_files[2];
    jlink_data.p_file_model = &jlink_files[3];
    jlink_data.p_file_shieldpose = &jlink_files[4];
    jlink_data.p_file_special1 = &jlink_files[5];
    jlink_data.p_file_special2 = &jlink_files[6];
    jlink_data.p_file_special3 = &jlink_files[7];
    jlink_data.p_file_special4 = &jlink_files[8];
    jlink_data.p_particle = &jlink_particle;
    desc.ft_data = &jlink_data;
    remix_jlink_relocate_scripts();
    port_fighter_register(NATIVE_REMIX_JLINK_KIND, &desc);
    port_log("REMIX PROBE: native J Link registered at fkind %u\n", NATIVE_REMIX_JLINK_KIND);
}

