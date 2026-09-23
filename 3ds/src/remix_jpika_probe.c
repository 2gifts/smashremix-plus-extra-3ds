/* Japanese Pikachu variant from the pinned Remix reference ROM. Its unique
 * action scripts and assets are generated locally, while the two regional
 * gameplay differences are translated from JPika.asm to native C. */
#include <ft/fighter.h>
#include <string.h>
#include "fighter_registry.h"
#include "native_remix_roster.h"

extern u32 portRelocRegisterPointer(void *);
extern void port_log(const char *, ...);
#include "jpika_data.inc"

enum {
    JPIKA_SPECIAL_FIRST = nFTCommonStatusSpecialStart,
    JPIKA_SPECIAL_LAST = nFTPikachuStatusSpecialAirHiEnd,
    JPIKA_SPECIAL_COUNT = JPIKA_SPECIAL_LAST - JPIKA_SPECIAL_FIRST + 1
};
_Static_assert(JPIKA_SPECIAL_COUNT == 18, "J Pikachu status table must follow vanilla Pikachu");

static FTStatusDesc jpika_status[JPIKA_SPECIAL_COUNT];
static FTData jpika_data;
static void *jpika_files[9];
static s32 jpika_particle;

int nativeRemixJPikaIsAnimation(unsigned fid) {
    if (!fid) return 0;
    for (unsigned i = 0; i < ARRAY_COUNT(remix_jpika_main_motions); i++)
        if (remix_jpika_main_motions[i].anim_file_id == fid &&
            !(remix_jpika_main_motions[i].anim_desc.word & (FTANIM_FLAG_ANIMJOINT | FTANIM_FLAG_SHIELDPOSE))) return 1;
    for (unsigned i = 0; i < ARRAY_COUNT(remix_jpika_menu_motions); i++)
        if (remix_jpika_menu_motions[i].anim_file_id == fid &&
            !(remix_jpika_menu_motions[i].anim_desc.word & (FTANIM_FLAG_ANIMJOINT | FTANIM_FLAG_SHIELDPOSE))) return 1;
    return 0;
}

/* JPikaUSP.JPika_SpecialHiProcMap_ uses the Japanese collision flow: after
 * leaving the floor it still runs the wall-end check. The US parent has an
 * else-if there. Preserve the mod's order rather than changing Pikachu. */
static void jpikaQuickAttackMap(GObj *gobj) {
    FTStruct *fp = ftGetStruct(gobj);
    if (mpCommonCheckFighterOnFloor(gobj) == FALSE) {
        if (fp->coll_data.mask_curr & (MAP_FLAG_RWALL | MAP_FLAG_LWALL)) {
            mpCommonSetFighterAir(fp);
            ftPikachuSpecialAirHiEndSetStatus(gobj);
        } else ftPikachuSpecialHiSwitchStatusAir(gobj);
    }
    if (fp->coll_data.mask_curr & (MAP_FLAG_RWALL | MAP_FLAG_LWALL))
        ftPikachuSpecialHiEndSetStatus(gobj);
}

void nativeRemixJPikaInit(void) {
    FighterDescriptor desc = *port_fighter_descriptor(nFTKindPikachu);
    jpika_data = *desc.ft_data;
    memcpy(&jpika_data.file_main_id, remix_jpika_files, sizeof(remix_jpika_files));
    jpika_data.o_attributes = REMIX_JPIKA_ATTRIBUTE_OFFSET;
    jpika_data.mainmotion = (FTMotionDescArray *)remix_jpika_main_motions;
    jpika_data.mainmotion_array_count = ARRAY_COUNT(remix_jpika_main_motions);
    jpika_data.submotion = (FTMotionDescArray *)remix_jpika_menu_motions;
    jpika_data.submotion_array_count = &remix_jpika_menu_count;
    jpika_data.p_file_main = &jpika_files[0];
    jpika_data.p_file_mainmotion = &jpika_files[1];
    jpika_data.p_file_submotion = &jpika_files[2];
    jpika_data.p_file_model = &jpika_files[3];
    jpika_data.p_file_shieldpose = &jpika_files[4];
    jpika_data.p_file_special1 = &jpika_files[5];
    jpika_data.p_file_special2 = &jpika_files[6];
    jpika_data.p_file_special3 = &jpika_files[7];
    jpika_data.p_file_special4 = &jpika_files[8];
    jpika_data.p_particle = &jpika_particle;
    desc.ft_data = &jpika_data;

    remix_jpika_relocate_scripts();
    memcpy(jpika_status, desc.special_descs, sizeof(jpika_status));
    jpika_status[nFTPikachuStatusSpecialHi - JPIKA_SPECIAL_FIRST].proc_map = jpikaQuickAttackMap;
    desc.special_descs = jpika_status;
    desc.special_descs_count = ARRAY_COUNT(jpika_status);
    port_fighter_register(NATIVE_REMIX_JPIKA_KIND, &desc);
    port_log("REMIX PROBE: native J Pikachu registered at fkind %u\n", NATIVE_REMIX_JPIKA_KIND);
}
