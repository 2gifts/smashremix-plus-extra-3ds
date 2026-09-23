#pragma once
/* Generated from remix/native_fighters.json. Run native_fighter_catalog.py to update. */
/* Temporary parent-card selector until the expanded Remix CSS is native. */
#define NATIVE_REMIX_MARIO_KIND 0u
#define NATIVE_REMIX_FOX_KIND 1u
#define NATIVE_REMIX_DONKEY_KIND 2u
#define NATIVE_REMIX_SAMUS_KIND 3u
#define NATIVE_REMIX_LUIGI_KIND 4u
#define NATIVE_REMIX_LINK_KIND 5u
#define NATIVE_REMIX_YOSHI_KIND 6u
#define NATIVE_REMIX_CAPTAIN_KIND 7u
#define NATIVE_REMIX_PIKACHU_KIND 9u
#define NATIVE_REMIX_JIGGLYPUFF_KIND 10u
#define NATIVE_REMIX_NESS_KIND 11u
#define NATIVE_REMIX_FALCO_KIND 29u
#define NATIVE_REMIX_JFOX_KIND 41u
#define NATIVE_REMIX_DKULT_KIND 81u
#define NATIVE_REMIX_JDK_KIND 44u
#define NATIVE_REMIX_JSAMUS_KIND 36u
#define NATIVE_REMIX_ESAMUS_KIND 51u
#define NATIVE_REMIX_ELINK_KIND 35u
#define NATIVE_REMIX_JLINK_KIND 39u
#define NATIVE_REMIX_JYOSHI_KIND 49u
#define NATIVE_REMIX_JPIKA_KIND 50u
#define NATIVE_REMIX_EPIKA_KIND 45u
#define NATIVE_REMIX_JMARIO_KIND 42u
#define NATIVE_REMIX_JFALCON_KIND 40u
#define NATIVE_REMIX_JLUIGI_KIND 43u
#define NATIVE_REMIX_JNESS_KIND 37u
#define NATIVE_REMIX_JPUFF_KIND 46u
#define NATIVE_REMIX_EPUFF_KIND 47u
#define NATIVE_REMIX_VS_CSS_SCENE 16u
extern volatile unsigned native_remix_selected_fkind[4];
int nativeRemixKirbyStarDamage(unsigned fkind);

typedef struct NativeRemixVariant {
    unsigned fkind;
    unsigned parent;
} NativeRemixVariant;

static const NativeRemixVariant native_remix_variants[] = {
    {NATIVE_REMIX_FALCO_KIND, NATIVE_REMIX_FOX_KIND},
    {NATIVE_REMIX_JFOX_KIND, NATIVE_REMIX_FOX_KIND},
    {NATIVE_REMIX_DKULT_KIND, NATIVE_REMIX_DONKEY_KIND},
    {NATIVE_REMIX_JDK_KIND, NATIVE_REMIX_DONKEY_KIND},
    {NATIVE_REMIX_JSAMUS_KIND, NATIVE_REMIX_SAMUS_KIND},
    {NATIVE_REMIX_ESAMUS_KIND, NATIVE_REMIX_SAMUS_KIND},
    {NATIVE_REMIX_ELINK_KIND, NATIVE_REMIX_LINK_KIND},
    {NATIVE_REMIX_JLINK_KIND, NATIVE_REMIX_LINK_KIND},
    {NATIVE_REMIX_JYOSHI_KIND, NATIVE_REMIX_YOSHI_KIND},
    {NATIVE_REMIX_JPIKA_KIND, NATIVE_REMIX_PIKACHU_KIND},
    {NATIVE_REMIX_EPIKA_KIND, NATIVE_REMIX_PIKACHU_KIND},
    {NATIVE_REMIX_JMARIO_KIND, NATIVE_REMIX_MARIO_KIND},
    {NATIVE_REMIX_JFALCON_KIND, NATIVE_REMIX_CAPTAIN_KIND},
    {NATIVE_REMIX_JLUIGI_KIND, NATIVE_REMIX_LUIGI_KIND},
    {NATIVE_REMIX_JNESS_KIND, NATIVE_REMIX_NESS_KIND},
    {NATIVE_REMIX_JPUFF_KIND, NATIVE_REMIX_JIGGLYPUFF_KIND},
    {NATIVE_REMIX_EPUFF_KIND, NATIVE_REMIX_JIGGLYPUFF_KIND},
};

static inline unsigned nativeRemixParentKind(unsigned fkind) {
    switch (fkind) {
    case NATIVE_REMIX_FALCO_KIND: return NATIVE_REMIX_FOX_KIND;
    case NATIVE_REMIX_JFOX_KIND: return NATIVE_REMIX_FOX_KIND;
    case NATIVE_REMIX_DKULT_KIND: return NATIVE_REMIX_DONKEY_KIND;
    case NATIVE_REMIX_JDK_KIND: return NATIVE_REMIX_DONKEY_KIND;
    case NATIVE_REMIX_JSAMUS_KIND: return NATIVE_REMIX_SAMUS_KIND;
    case NATIVE_REMIX_ESAMUS_KIND: return NATIVE_REMIX_SAMUS_KIND;
    case NATIVE_REMIX_ELINK_KIND: return NATIVE_REMIX_LINK_KIND;
    case NATIVE_REMIX_JLINK_KIND: return NATIVE_REMIX_LINK_KIND;
    case NATIVE_REMIX_JYOSHI_KIND: return NATIVE_REMIX_YOSHI_KIND;
    case NATIVE_REMIX_JPIKA_KIND: return NATIVE_REMIX_PIKACHU_KIND;
    case NATIVE_REMIX_EPIKA_KIND: return NATIVE_REMIX_PIKACHU_KIND;
    case NATIVE_REMIX_JMARIO_KIND: return NATIVE_REMIX_MARIO_KIND;
    case NATIVE_REMIX_JFALCON_KIND: return NATIVE_REMIX_CAPTAIN_KIND;
    case NATIVE_REMIX_JLUIGI_KIND: return NATIVE_REMIX_LUIGI_KIND;
    case NATIVE_REMIX_JNESS_KIND: return NATIVE_REMIX_NESS_KIND;
    case NATIVE_REMIX_JPUFF_KIND: return NATIVE_REMIX_JIGGLYPUFF_KIND;
    case NATIVE_REMIX_EPUFF_KIND: return NATIVE_REMIX_JIGGLYPUFF_KIND;
    default: return fkind;
    }
}

static inline unsigned nativeRemixIsVariant(unsigned fkind) {
    return nativeRemixParentKind(fkind) != fkind;
}

static inline unsigned nativeRemixResolveKind(unsigned parent, unsigned selected) {
    for (unsigned i = 0; i < sizeof(native_remix_variants) / sizeof(native_remix_variants[0]); i++)
        if (native_remix_variants[i].fkind == selected && native_remix_variants[i].parent == parent)
            return selected;
    return parent;
}

static inline unsigned nativeRemixNextKind(unsigned card, unsigned selected) {
    unsigned parent = nativeRemixParentKind(card);
    unsigned first = 0, found = 0;
    for (unsigned i = 0; i < sizeof(native_remix_variants) / sizeof(native_remix_variants[0]); i++) {
        if (native_remix_variants[i].parent != parent) continue;
        if (!first) first = native_remix_variants[i].fkind;
        if (found) return native_remix_variants[i].fkind;
        if (native_remix_variants[i].fkind == selected) found = 1;
    }
    return found ? 0 : first;
}
