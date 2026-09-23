/* Japanese Luigi variant from the pinned Remix reference ROM. Its regional
 * jab, throws and up-special scripts and model are imported from the reference
 * build; vanilla Luigi supplies the unchanged action callbacks. */
#include <ft/fighter.h>
#include <string.h>
#include "fighter_registry.h"
#include "native_remix_roster.h"

extern u32 portRelocRegisterPointer(void *);
extern void port_log(const char *, ...);
#include "jluigi_data.inc"

static FTData jluigi_data;
static void *jluigi_files[9];
static s32 jluigi_particle;

int nativeRemixJLuigiIsAnimation(unsigned fid) {
    if (!fid) return 0;
    for (unsigned i = 0; i < ARRAY_COUNT(remix_jluigi_main_motions); i++)
        if (remix_jluigi_main_motions[i].anim_file_id == fid &&
            !(remix_jluigi_main_motions[i].anim_desc.word & (FTANIM_FLAG_ANIMJOINT | FTANIM_FLAG_SHIELDPOSE))) return 1;
    for (unsigned i = 0; i < ARRAY_COUNT(remix_jluigi_menu_motions); i++)
        if (remix_jluigi_menu_motions[i].anim_file_id == fid &&
            !(remix_jluigi_menu_motions[i].anim_desc.word & (FTANIM_FLAG_ANIMJOINT | FTANIM_FLAG_SHIELDPOSE))) return 1;
    return 0;
}

void nativeRemixJLuigiInit(void) {
    FighterDescriptor desc = *port_fighter_descriptor(nFTKindLuigi);
    jluigi_data = *desc.ft_data;
    memcpy(&jluigi_data.file_main_id, remix_jluigi_files, sizeof(remix_jluigi_files));
    jluigi_data.o_attributes = REMIX_JLUIGI_ATTRIBUTE_OFFSET;
    jluigi_data.mainmotion = (FTMotionDescArray *)remix_jluigi_main_motions;
    jluigi_data.mainmotion_array_count = ARRAY_COUNT(remix_jluigi_main_motions);
    jluigi_data.submotion = (FTMotionDescArray *)remix_jluigi_menu_motions;
    jluigi_data.submotion_array_count = &remix_jluigi_menu_count;
    jluigi_data.p_file_main = &jluigi_files[0];
    jluigi_data.p_file_mainmotion = &jluigi_files[1];
    jluigi_data.p_file_submotion = &jluigi_files[2];
    jluigi_data.p_file_model = &jluigi_files[3];
    jluigi_data.p_file_shieldpose = &jluigi_files[4];
    jluigi_data.p_file_special1 = &jluigi_files[5];
    jluigi_data.p_file_special2 = &jluigi_files[6];
    jluigi_data.p_file_special3 = &jluigi_files[7];
    jluigi_data.p_file_special4 = &jluigi_files[8];
    jluigi_data.p_particle = &jluigi_particle;
    desc.ft_data = &jluigi_data;
    remix_jluigi_relocate_scripts();
    port_fighter_register(NATIVE_REMIX_JLUIGI_KIND, &desc);
    port_log("REMIX PROBE: native J Luigi registered at fkind %u\n", NATIVE_REMIX_JLUIGI_KIND);
}
