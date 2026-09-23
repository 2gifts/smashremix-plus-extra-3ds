/* Electric Link from the pinned Remix reference ROM. Its independently
 * backed motion data includes the modified forward-smash script. */
#include <ft/fighter.h>
#include <string.h>
#include "fighter_registry.h"
#include "native_remix_roster.h"

extern u32 portRelocRegisterPointer(void *);
extern void port_log(const char *, ...);
#include "elink_data.inc"

static FTData elink_data;
static void *elink_files[9];
static s32 elink_particle;

int nativeRemixELinkIsAnimation(unsigned fid) {
    if (!fid) return 0;
    for (unsigned i = 0; i < ARRAY_COUNT(remix_elink_main_motions); i++)
        if (remix_elink_main_motions[i].anim_file_id == fid &&
            !(remix_elink_main_motions[i].anim_desc.word & (FTANIM_FLAG_ANIMJOINT | FTANIM_FLAG_SHIELDPOSE))) return 1;
    for (unsigned i = 0; i < ARRAY_COUNT(remix_elink_menu_motions); i++)
        if (remix_elink_menu_motions[i].anim_file_id == fid &&
            !(remix_elink_menu_motions[i].anim_desc.word & (FTANIM_FLAG_ANIMJOINT | FTANIM_FLAG_SHIELDPOSE))) return 1;
    return 0;
}

void nativeRemixELinkInit(void) {
    FighterDescriptor desc = *port_fighter_descriptor(nFTKindLink);
    elink_data = *desc.ft_data;
    memcpy(&elink_data.file_main_id, remix_elink_files, sizeof(remix_elink_files));
    elink_data.o_attributes = REMIX_ELINK_ATTRIBUTE_OFFSET;
    elink_data.mainmotion = (FTMotionDescArray *)remix_elink_main_motions;
    elink_data.mainmotion_array_count = ARRAY_COUNT(remix_elink_main_motions);
    elink_data.submotion = (FTMotionDescArray *)remix_elink_menu_motions;
    elink_data.submotion_array_count = &remix_elink_menu_count;
    elink_data.p_file_main = &elink_files[0];
    elink_data.p_file_mainmotion = &elink_files[1];
    elink_data.p_file_submotion = &elink_files[2];
    elink_data.p_file_model = &elink_files[3];
    elink_data.p_file_shieldpose = &elink_files[4];
    elink_data.p_file_special1 = &elink_files[5];
    elink_data.p_file_special2 = &elink_files[6];
    elink_data.p_file_special3 = &elink_files[7];
    elink_data.p_file_special4 = &elink_files[8];
    elink_data.p_particle = &elink_particle;
    desc.ft_data = &elink_data;
    remix_elink_relocate_scripts();
    port_fighter_register(NATIVE_REMIX_ELINK_KIND, &desc);
    port_log("REMIX PROBE: native E Link registered at fkind %u\n", NATIVE_REMIX_ELINK_KIND);
}
