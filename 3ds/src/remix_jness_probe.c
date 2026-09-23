/* Japanese Ness from the pinned Remix reference ROM. Regional attack scripts,
 * PK Thunder 2, attributes and projectile assets are independently backed. */
#include <ft/fighter.h>
#include <string.h>
#include "fighter_registry.h"
#include "native_remix_roster.h"

extern u32 portRelocRegisterPointer(void *);
extern void port_log(const char *, ...);
#include "jness_data.inc"

static FTData jness_data;
static void *jness_files[9];
static s32 jness_particle;

int nativeRemixJNessIsAnimation(unsigned fid) {
    if (!fid) return 0;
    for (unsigned i = 0; i < ARRAY_COUNT(remix_jness_main_motions); i++)
        if (remix_jness_main_motions[i].anim_file_id == fid &&
            !(remix_jness_main_motions[i].anim_desc.word & (FTANIM_FLAG_ANIMJOINT | FTANIM_FLAG_SHIELDPOSE))) return 1;
    for (unsigned i = 0; i < ARRAY_COUNT(remix_jness_menu_motions); i++)
        if (remix_jness_menu_motions[i].anim_file_id == fid &&
            !(remix_jness_menu_motions[i].anim_desc.word & (FTANIM_FLAG_ANIMJOINT | FTANIM_FLAG_SHIELDPOSE))) return 1;
    return 0;
}

void nativeRemixJNessInit(void) {
    FighterDescriptor desc = *port_fighter_descriptor(nFTKindNess);
    jness_data = *desc.ft_data;
    /* The mod places Magnet in special slot 1 and its new PK Fire art in
     * special slot 2, opposite the vanilla Ness file layout. */
    memcpy(&jness_data.file_main_id, remix_jness_files, sizeof(remix_jness_files));
    jness_data.o_attributes = REMIX_JNESS_ATTRIBUTE_OFFSET;
    jness_data.mainmotion = (FTMotionDescArray *)remix_jness_main_motions;
    jness_data.mainmotion_array_count = ARRAY_COUNT(remix_jness_main_motions);
    jness_data.submotion = (FTMotionDescArray *)remix_jness_menu_motions;
    jness_data.submotion_array_count = &remix_jness_menu_count;
    jness_data.p_file_main = &jness_files[0];
    jness_data.p_file_mainmotion = &jness_files[1];
    jness_data.p_file_submotion = &jness_files[2];
    jness_data.p_file_model = &jness_files[3];
    jness_data.p_file_shieldpose = &jness_files[4];
    jness_data.p_file_special1 = &jness_files[5];
    jness_data.p_file_special2 = &jness_files[6];
    jness_data.p_file_special3 = &jness_files[7];
    jness_data.p_file_special4 = &jness_files[8];
    jness_data.p_particle = &jness_particle;
    desc.ft_data = &jness_data;
    remix_jness_relocate_scripts();
    port_fighter_register(NATIVE_REMIX_JNESS_KIND, &desc);
    port_log("REMIX PROBE: native J Ness registered at fkind %u\n", NATIVE_REMIX_JNESS_KIND);
}
