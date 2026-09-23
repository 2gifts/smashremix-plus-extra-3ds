/* Electric Samus from the pinned Remix reference ROM. Its independently
 * backed data supplies the regional back and down aerial motion scripts. */
#include <ft/fighter.h>
#include <string.h>
#include "fighter_registry.h"
#include "native_remix_roster.h"

extern u32 portRelocRegisterPointer(void *);
extern void port_log(const char *, ...);
#include "esamus_data.inc"

static FTData esamus_data;
static void *esamus_files[9];
static s32 esamus_particle;

int nativeRemixESamusIsAnimation(unsigned fid) {
    if (!fid) return 0;
    for (unsigned i = 0; i < ARRAY_COUNT(remix_esamus_main_motions); i++)
        if (remix_esamus_main_motions[i].anim_file_id == fid &&
            !(remix_esamus_main_motions[i].anim_desc.word & (FTANIM_FLAG_ANIMJOINT | FTANIM_FLAG_SHIELDPOSE))) return 1;
    for (unsigned i = 0; i < ARRAY_COUNT(remix_esamus_menu_motions); i++)
        if (remix_esamus_menu_motions[i].anim_file_id == fid &&
            !(remix_esamus_menu_motions[i].anim_desc.word & (FTANIM_FLAG_ANIMJOINT | FTANIM_FLAG_SHIELDPOSE))) return 1;
    return 0;
}

void nativeRemixESamusInit(void) {
    FighterDescriptor desc = *port_fighter_descriptor(nFTKindSamus);
    esamus_data = *desc.ft_data;
    memcpy(&esamus_data.file_main_id, remix_esamus_files, sizeof(remix_esamus_files));
    esamus_data.o_attributes = REMIX_ESAMUS_ATTRIBUTE_OFFSET;
    esamus_data.mainmotion = (FTMotionDescArray *)remix_esamus_main_motions;
    esamus_data.mainmotion_array_count = ARRAY_COUNT(remix_esamus_main_motions);
    esamus_data.submotion = (FTMotionDescArray *)remix_esamus_menu_motions;
    esamus_data.submotion_array_count = &remix_esamus_menu_count;
    esamus_data.p_file_main = &esamus_files[0];
    esamus_data.p_file_mainmotion = &esamus_files[1];
    esamus_data.p_file_submotion = &esamus_files[2];
    esamus_data.p_file_model = &esamus_files[3];
    esamus_data.p_file_shieldpose = &esamus_files[4];
    esamus_data.p_file_special1 = &esamus_files[5];
    esamus_data.p_file_special2 = &esamus_files[6];
    esamus_data.p_file_special3 = &esamus_files[7];
    esamus_data.p_file_special4 = &esamus_files[8];
    esamus_data.p_particle = &esamus_particle;
    desc.ft_data = &esamus_data;
    remix_esamus_relocate_scripts();
    port_fighter_register(NATIVE_REMIX_ESAMUS_KIND, &desc);
    port_log("REMIX PROBE: native E Samus registered at fkind %u\n", NATIVE_REMIX_ESAMUS_KIND);
}
