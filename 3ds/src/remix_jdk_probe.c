/* Japanese Donkey Kong from the pinned Remix reference ROM. Its regional
 * aerial scripts and model are imported from the reference build; native C
 * selects the Japanese Spinning Kong lift and cargo-hold escape resistance. */
#include <ft/fighter.h>
#include <string.h>
#include "fighter_registry.h"
#include "native_remix_roster.h"

extern u32 portRelocRegisterPointer(void *);
extern void port_log(const char *, ...);
#include "jdk_data.inc"

static FTData jdk_data;
static void *jdk_files[9];
static s32 jdk_particle;

int nativeRemixJDKIsAnimation(unsigned fid) {
    if (!fid) return 0;
    for (unsigned i = 0; i < ARRAY_COUNT(remix_jdk_main_motions); i++)
        if (remix_jdk_main_motions[i].anim_file_id == fid &&
            !(remix_jdk_main_motions[i].anim_desc.word & (FTANIM_FLAG_ANIMJOINT | FTANIM_FLAG_SHIELDPOSE))) return 1;
    for (unsigned i = 0; i < ARRAY_COUNT(remix_jdk_menu_motions); i++)
        if (remix_jdk_menu_motions[i].anim_file_id == fid &&
            !(remix_jdk_menu_motions[i].anim_desc.word & (FTANIM_FLAG_ANIMJOINT | FTANIM_FLAG_SHIELDPOSE))) return 1;
    return 0;
}

void nativeRemixJDKInit(void) {
    FighterDescriptor desc = *port_fighter_descriptor(nFTKindDonkey);
    jdk_data = *desc.ft_data;
    memcpy(&jdk_data.file_main_id, remix_jdk_files, sizeof(remix_jdk_files));
    jdk_data.o_attributes = REMIX_JDK_ATTRIBUTE_OFFSET;
    jdk_data.mainmotion = (FTMotionDescArray *)remix_jdk_main_motions;
    jdk_data.mainmotion_array_count = ARRAY_COUNT(remix_jdk_main_motions);
    jdk_data.submotion = (FTMotionDescArray *)remix_jdk_menu_motions;
    jdk_data.submotion_array_count = &remix_jdk_menu_count;
    jdk_data.p_file_main = &jdk_files[0];
    jdk_data.p_file_mainmotion = &jdk_files[1];
    jdk_data.p_file_submotion = &jdk_files[2];
    jdk_data.p_file_model = &jdk_files[3];
    jdk_data.p_file_shieldpose = &jdk_files[4];
    jdk_data.p_file_special1 = &jdk_files[5];
    jdk_data.p_file_special2 = &jdk_files[6];
    jdk_data.p_file_special3 = &jdk_files[7];
    jdk_data.p_file_special4 = &jdk_files[8];
    jdk_data.p_particle = &jdk_particle;
    desc.ft_data = &jdk_data;
    remix_jdk_relocate_scripts();
    port_fighter_register(NATIVE_REMIX_JDK_KIND, &desc);
    port_log("REMIX PROBE: native J DK registered at fkind %u\n", NATIVE_REMIX_JDK_KIND);
}
