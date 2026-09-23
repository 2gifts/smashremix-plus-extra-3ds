#pragma once
/* Temporary native selection bridge while the expanded Remix CSS is ported.
 * A zero entry keeps the original portrait's fighter. */
#define NATIVE_REMIX_FALCO_KIND 29u
#define NATIVE_REMIX_FOX_KIND 1u
#define NATIVE_REMIX_DKULT_KIND 81u
#define NATIVE_REMIX_JDK_KIND 44u
#define NATIVE_REMIX_DONKEY_KIND 2u
#define NATIVE_REMIX_JPIKA_KIND 50u
#define NATIVE_REMIX_EPIKA_KIND 45u
#define NATIVE_REMIX_PIKACHU_KIND 9u
#define NATIVE_REMIX_JMARIO_KIND 42u
#define NATIVE_REMIX_MARIO_KIND 0u
#define NATIVE_REMIX_JFALCON_KIND 40u
#define NATIVE_REMIX_CAPTAIN_KIND 7u
#define NATIVE_REMIX_JLUIGI_KIND 43u
#define NATIVE_REMIX_LUIGI_KIND 4u
#define NATIVE_REMIX_VS_CSS_SCENE 16u
extern volatile unsigned native_remix_selected_fkind[4];

/* The VS bottom cards temporarily host imported fighters until the expanded
 * Remix CSS is native. Keep match, HUD and results mapping in one ordered
 * list; each parent's entries define its card cycle. */
typedef struct NativeRemixVariant {
    unsigned fkind;
    unsigned parent;
} NativeRemixVariant;

static const NativeRemixVariant native_remix_variants[] = {
    {NATIVE_REMIX_FALCO_KIND, NATIVE_REMIX_FOX_KIND},
    {NATIVE_REMIX_DKULT_KIND, NATIVE_REMIX_DONKEY_KIND},
    {NATIVE_REMIX_JDK_KIND, NATIVE_REMIX_DONKEY_KIND},
    {NATIVE_REMIX_JPIKA_KIND, NATIVE_REMIX_PIKACHU_KIND},
    {NATIVE_REMIX_EPIKA_KIND, NATIVE_REMIX_PIKACHU_KIND},
    {NATIVE_REMIX_JMARIO_KIND, NATIVE_REMIX_MARIO_KIND},
    {NATIVE_REMIX_JFALCON_KIND, NATIVE_REMIX_CAPTAIN_KIND},
    {NATIVE_REMIX_JLUIGI_KIND, NATIVE_REMIX_LUIGI_KIND},
};

static inline unsigned nativeRemixParentKind(unsigned fkind) {
    for (unsigned i = 0; i < sizeof(native_remix_variants) / sizeof(native_remix_variants[0]); i++)
        if (native_remix_variants[i].fkind == fkind) return native_remix_variants[i].parent;
    return fkind;
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
