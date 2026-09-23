/* Japanese Captain Falcon from the pinned Remix reference ROM. Regional jab
 * motions and fighter assets are generated locally; the Captain callbacks
 * remain native and his Japanese Falcon Dive drift is selected by fkind. */
#include <ft/fighter.h>
#include <string.h>
#include "fighter_registry.h"
#include "native_remix_roster.h"

extern u32 portRelocRegisterPointer(void *);
extern void port_log(const char *, ...);
#include "jfalcon_data.inc"

static FTData jfalcon_data;
static void *jfalcon_files[9];
static s32 jfalcon_particle;

int nativeRemixJFalconIsAnimation(unsigned fid) {
    if (!fid) return 0;
    for (unsigned i = 0; i < ARRAY_COUNT(remix_jfalcon_main_motions); i++)
        if (remix_jfalcon_main_motions[i].anim_file_id == fid &&
            !(remix_jfalcon_main_motions[i].anim_desc.word & (FTANIM_FLAG_ANIMJOINT | FTANIM_FLAG_SHIELDPOSE))) return 1;
    for (unsigned i = 0; i < ARRAY_COUNT(remix_jfalcon_menu_motions); i++)
        if (remix_jfalcon_menu_motions[i].anim_file_id == fid &&
            !(remix_jfalcon_menu_motions[i].anim_desc.word & (FTANIM_FLAG_ANIMJOINT | FTANIM_FLAG_SHIELDPOSE))) return 1;
    return 0;
}

void nativeRemixJFalconInit(void) {
    FighterDescriptor desc = *port_fighter_descriptor(nFTKindCaptain);
    jfalcon_data = *desc.ft_data;
    memcpy(&jfalcon_data.file_main_id, remix_jfalcon_files, sizeof(remix_jfalcon_files));
    jfalcon_data.o_attributes = REMIX_JFALCON_ATTRIBUTE_OFFSET;
    jfalcon_data.mainmotion = (FTMotionDescArray *)remix_jfalcon_main_motions;
    jfalcon_data.mainmotion_array_count = ARRAY_COUNT(remix_jfalcon_main_motions);
    jfalcon_data.submotion = (FTMotionDescArray *)remix_jfalcon_menu_motions;
    jfalcon_data.submotion_array_count = &remix_jfalcon_menu_count;
    jfalcon_data.p_file_main = &jfalcon_files[0];
    jfalcon_data.p_file_mainmotion = &jfalcon_files[1];
    jfalcon_data.p_file_submotion = &jfalcon_files[2];
    jfalcon_data.p_file_model = &jfalcon_files[3];
    jfalcon_data.p_file_shieldpose = &jfalcon_files[4];
    jfalcon_data.p_file_special1 = &jfalcon_files[5];
    jfalcon_data.p_file_special2 = &jfalcon_files[6];
    jfalcon_data.p_file_special3 = &jfalcon_files[7];
    jfalcon_data.p_file_special4 = &jfalcon_files[8];
    jfalcon_data.p_particle = &jfalcon_particle;
    desc.ft_data = &jfalcon_data;
    remix_jfalcon_relocate_scripts();
    port_fighter_register(NATIVE_REMIX_JFALCON_KIND, &desc);
    port_log("REMIX PROBE: native J Falcon registered at fkind %u\n", NATIVE_REMIX_JFALCON_KIND);
}
