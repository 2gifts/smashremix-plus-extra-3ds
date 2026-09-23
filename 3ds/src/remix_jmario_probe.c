/* Japanese Mario variant from the pinned Remix reference ROM. Its regional
 * jab and back-throw scripts and model are imported from the reference build;
 * vanilla Mario supplies the unchanged action callbacks. */
#include <ft/fighter.h>
#include <string.h>
#include "fighter_registry.h"
#include "native_remix_roster.h"

extern u32 portRelocRegisterPointer(void *);
extern void port_log(const char *, ...);
#include "jmario_data.inc"

static FTData jmario_data;
static void *jmario_files[9];
static s32 jmario_particle;

int nativeRemixJMarioIsAnimation(unsigned fid) {
    if (!fid) return 0;
    for (unsigned i = 0; i < ARRAY_COUNT(remix_jmario_main_motions); i++)
        if (remix_jmario_main_motions[i].anim_file_id == fid &&
            !(remix_jmario_main_motions[i].anim_desc.word & (FTANIM_FLAG_ANIMJOINT | FTANIM_FLAG_SHIELDPOSE))) return 1;
    for (unsigned i = 0; i < ARRAY_COUNT(remix_jmario_menu_motions); i++)
        if (remix_jmario_menu_motions[i].anim_file_id == fid &&
            !(remix_jmario_menu_motions[i].anim_desc.word & (FTANIM_FLAG_ANIMJOINT | FTANIM_FLAG_SHIELDPOSE))) return 1;
    return 0;
}

void nativeRemixJMarioInit(void) {
    FighterDescriptor desc = *port_fighter_descriptor(nFTKindMario);
    jmario_data = *desc.ft_data;
    memcpy(&jmario_data.file_main_id, remix_jmario_files, sizeof(remix_jmario_files));
    jmario_data.o_attributes = REMIX_JMARIO_ATTRIBUTE_OFFSET;
    jmario_data.mainmotion = (FTMotionDescArray *)remix_jmario_main_motions;
    jmario_data.mainmotion_array_count = ARRAY_COUNT(remix_jmario_main_motions);
    jmario_data.submotion = (FTMotionDescArray *)remix_jmario_menu_motions;
    jmario_data.submotion_array_count = &remix_jmario_menu_count;
    jmario_data.p_file_main = &jmario_files[0];
    jmario_data.p_file_mainmotion = &jmario_files[1];
    jmario_data.p_file_submotion = &jmario_files[2];
    jmario_data.p_file_model = &jmario_files[3];
    jmario_data.p_file_shieldpose = &jmario_files[4];
    jmario_data.p_file_special1 = &jmario_files[5];
    jmario_data.p_file_special2 = &jmario_files[6];
    jmario_data.p_file_special3 = &jmario_files[7];
    jmario_data.p_file_special4 = &jmario_files[8];
    jmario_data.p_particle = &jmario_particle;
    desc.ft_data = &jmario_data;
    remix_jmario_relocate_scripts();
    port_fighter_register(NATIVE_REMIX_JMARIO_KIND, &desc);
    port_log("REMIX PROBE: native J Mario registered at fkind %u\n", NATIVE_REMIX_JMARIO_KIND);
}
