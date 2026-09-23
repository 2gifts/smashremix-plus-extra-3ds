/* Electric Pikachu from the pinned Remix reference ROM. The independently
 * imported fighter data carries its aerial, smash, tilt and Thunder scripts. */
#include <ft/fighter.h>
#include <string.h>
#include "fighter_registry.h"
#include "native_remix_roster.h"

extern u32 portRelocRegisterPointer(void *);
extern void port_log(const char *, ...);
#include "epika_data.inc"

static FTData epika_data;
static void *epika_files[9];
static s32 epika_particle;

int nativeRemixEPikaIsAnimation(unsigned fid) {
    if (!fid) return 0;
    for (unsigned i = 0; i < ARRAY_COUNT(remix_epika_main_motions); i++)
        if (remix_epika_main_motions[i].anim_file_id == fid &&
            !(remix_epika_main_motions[i].anim_desc.word & (FTANIM_FLAG_ANIMJOINT | FTANIM_FLAG_SHIELDPOSE))) return 1;
    for (unsigned i = 0; i < ARRAY_COUNT(remix_epika_menu_motions); i++)
        if (remix_epika_menu_motions[i].anim_file_id == fid &&
            !(remix_epika_menu_motions[i].anim_desc.word & (FTANIM_FLAG_ANIMJOINT | FTANIM_FLAG_SHIELDPOSE))) return 1;
    return 0;
}

void nativeRemixEPikaInit(void) {
    FighterDescriptor desc = *port_fighter_descriptor(nFTKindPikachu);
    epika_data = *desc.ft_data;
    memcpy(&epika_data.file_main_id, remix_epika_files, sizeof(remix_epika_files));
    epika_data.o_attributes = REMIX_EPIKA_ATTRIBUTE_OFFSET;
    epika_data.mainmotion = (FTMotionDescArray *)remix_epika_main_motions;
    epika_data.mainmotion_array_count = ARRAY_COUNT(remix_epika_main_motions);
    epika_data.submotion = (FTMotionDescArray *)remix_epika_menu_motions;
    epika_data.submotion_array_count = &remix_epika_menu_count;
    epika_data.p_file_main = &epika_files[0];
    epika_data.p_file_mainmotion = &epika_files[1];
    epika_data.p_file_submotion = &epika_files[2];
    epika_data.p_file_model = &epika_files[3];
    epika_data.p_file_shieldpose = &epika_files[4];
    epika_data.p_file_special1 = &epika_files[5];
    epika_data.p_file_special2 = &epika_files[6];
    epika_data.p_file_special3 = &epika_files[7];
    epika_data.p_file_special4 = &epika_files[8];
    epika_data.p_particle = &epika_particle;
    desc.ft_data = &epika_data;
    remix_epika_relocate_scripts();
    port_fighter_register(NATIVE_REMIX_EPIKA_KIND, &desc);
    port_log("REMIX PROBE: native E Pikachu registered at fkind %u\n", NATIVE_REMIX_EPIKA_KIND);
}
