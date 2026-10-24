#version 460 core
#extension GL_EXT_samplerless_texture_functions : require

// Based on CAS_Shader.glsl
// Copyright(c) 2019 Advanced Micro Devices, Inc.All rights reserved.
// Permission is hereby granted, free of charge, to any person obtaining a copy
// of this software and associated documentation files(the "Software"), to deal
// in the Software without restriction, including without limitation the rights
// to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
// copies of the Software, and to permit persons to whom the Software is
// furnished to do so, subject to the following conditions :
// The above copyright notice and this permission notice shall be included in
// all copies or substantial portions of the Software.
// THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
// IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
// FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.IN NO EVENT SHALL THE
// AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
// LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
// OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
// THE SOFTWARE.

// ---------------------------------------------------------------------------------------------
// Varianta laděná pro PS2 (výstup emulátoru je gamma-kódovaný, nízké rozlišení, jemný šum).
//
// Rozhraní je beze změny: push constanty (const0, const1, srcOffset), bindingy a spec constant
// sharpenOnly jsou stejné jako v originále, takže CasSetup() na straně hostitele (ffx_cas.h)
// funguje dál a posuvník ostrosti se chová stejně. ffx_cas.h se v tomto shaderu už nevkládá,
// filtr je zde přímo; ffx_a.h zůstává (aproximace rcp/sqrt a swizzle jsou ze stejných funkcí).
// Počet čtení textury se nemění (5 v sharpen-only, 12 při škálování), žádný další průchod.
//
// Všechny úpravy jdou vypnout; s PS2_CORING=0 (a lineárními přepínači na 0) je výstup bit po bitu
// shodný s původním CAS (ověřeno porovnáním na softwarovém Vulkanu (lavapipe), oba režimy, ostrost 0 / 0.5 / 1).
// ---------------------------------------------------------------------------------------------

// Coring: tam, kde je lokální rozsah hodnot (max - min kříže, v kanálu G) jen pár úrovní z 255,
// se neostří. Takové "detaily" jsou prakticky vždy šum, schody kvantizace 8bit gradientů nebo
// dither, a CAS by je zesiloval. Skutečná jemná textura má rozsah výrazně větší a projde.
// Prahy jsou v jednotkách gamma-kódované hodnoty 0..1:
//   rozsah pod LO se neostří vůbec, nad HI naplno, mezi tím plynule (smoothstep).
//   Větší HI = čistší plochy, ale i méně doostřených velmi slabých detailů.
// (16bit dither PS2 má amplitudu ~±4/255, tedy rozsah ~8 úrovní; tím se tento práh nezbavíš.)
// Ve sharpen-only je coring plynulý přechod mezi neostřeným a ostřeným pixelem; při zvětšení
// funguje jako brána po 4 středech (viz Ps2CasScale).
#ifndef PS2_CORING
#define PS2_CORING 1
#endif
#ifndef PS2_CORE_LO
#define PS2_CORE_LO (2.0/255.0)
#endif
#ifndef PS2_CORE_HI
#define PS2_CORE_HI (5.0/255.0)
#endif

// Zpracování v lineárním světle (aproximace gamma 2.0, jak doporučuje ffx_cas.h pro UNORM data).
// Obojí je ve výchozím stavu VYPNUTÉ, protože to mění vzhled; jde o vyvážení, ne o čisté zlepšení.
//  PS2_LINEAR_SCALE   (zvětšení): interpolace v lineárním světle zachová světlé tenké detaily
//      (bílý text HUD, světlé čáry se při zvětšení nezužují: světlo celého snímku -12 % -> -2 %
//      na testu pruhů), ale tenké TMAVÉ čáry jsou po zvětšení světlejší (obrysy cel-shaded her,
//      stíny písma; v testu 2x nejtmavší bod čáry 49 -> 87). Zapni, pokud ti záleží víc na prvním.
//  PS2_LINEAR_SHARPEN (sharpen-only): menší světlé halo kolem hran (překmit 18 -> 5 úrovní
//      při ostrosti 0.5), ale o něco výraznější tmavý lem (18 -> 20) a mírnější dojem z posuvníku.
#ifndef PS2_LINEAR_SCALE
#define PS2_LINEAR_SCALE 0
#endif
#ifndef PS2_LINEAR_SHARPEN
#define PS2_LINEAR_SHARPEN 0
#endif

layout(push_constant) uniform const_buffer
{
    uvec4 const0;
    uvec4 const1;
    ivec2 srcOffset;
};

layout(set=0, binding=0) uniform texture2D imgSrc;
layout(set=0, binding=1, rgba8) uniform writeonly image2D imgDst;
layout(constant_id=0) const int sharpenOnly = 0;

#define A_GPU 1
#define A_GLSL 1

#include "ffx_a.h"

// Vstup načítáme gamma-kódovaný (tak, jak ho dodá emulátor); převod do lineárního prostoru
// (pokud je zapnutý) se dělá až po výpočtu coringu, který potřebuje původní gamma hodnoty.
AF3 CasLoad(ASU2 p)
{
    return texelFetch(imgSrc, srcOffset + ivec2(p), 0).rgb;
}

// Váha coringu 0..1 z lokálního rozsahu hodnot (gamma doména).
AF1 Ps2Core(AF1 range)
{
#if PS2_CORING
    return smoothstep(AF1_(PS2_CORE_LO), AF1_(PS2_CORE_HI), range);
#else
    return AF1_(1.0);
#endif
}

//==============================================================================================
// Pouze doostření (bez změny velikosti): minimální okolí 3x3, používá se kříž b,d,e,f,h.
//   a b c
//   d e f
//   g h i
//==============================================================================================
AF3 Ps2CasSharpen(AU2 ip, AU4 c1)
{
    ASU2 sp = ASU2(ip);
    AF3 b = CasLoad(sp + ASU2( 0,-1));
    AF3 d = CasLoad(sp + ASU2(-1, 0));
    AF3 e = CasLoad(sp);
    AF3 f = CasLoad(sp + ASU2( 1, 0));
    AF3 h = CasLoad(sp + ASU2( 0, 1));

    // Hard min a max kříže (v originále bez CAS_BETTER_DIAGONALS); pro váhy se používá jen G.
    // Počítá se z gamma hodnot, z rozsahu se bere coring; do lineárního prostoru se pak převádí
    // jen min a max (kvadrát je monotónní, takže min(x*x) == min(x)*min(x)).
    AF1 mnG = AMin3F1(AMin3F1(d.g, e.g, f.g), b.g, h.g);
    AF1 mxG = AMax3F1(AMax3F1(d.g, e.g, f.g), b.g, h.g);
    AF1 core = Ps2Core(mxG - mnG);

#if PS2_LINEAR_SHARPEN
    b *= b; d *= d; e *= e; f *= f; h *= h;
    mnG *= mnG; mxG *= mxG;
#endif

    AF1 ampG = ASatF1(min(mnG, AF1_(1.0) - mxG) * APrxLoRcpF1(mxG));
    ampG = APrxLoSqrtF1(ampG);

    // Tvar filtru:  0 w 0 / w 1 w / 0 w 0   (w záporné, síla z push constanty const1.x)
    AF1 peak = AF1_AU1(c1.x);
    AF1 wG = ampG * peak;
    AF1 rcpWeight = APrxMedRcpF1(AF1_(1.0) + AF1_(4.0) * wG);
    AF3 sharp = clamp((b * wG + d * wG + f * wG + h * wG + e) * rcpWeight, AF1_(0.0), AF1_(1.0));

    // Coring: plynulý přechod mezi neostřeným a ostřeným pixelem (při core=0 přesně e).
#if PS2_CORING
    sharp = mix(e, sharp, core);
#endif

#if PS2_LINEAR_SHARPEN
    sharp = sqrt(sharp);
#endif
    return sharp;
}

//==============================================================================================
// Zvětšení + doostření: adaptivní interpolace mezi 4 nejbližšími výsledky nescalovaného filtru.
//   a b c d
//   e f g h      výstupní pixel leží uvnitř čtverce f g / j k
//   i j k l
//   m n o p      (rohy a,d,m,p se bez CAS_BETTER_DIAGONALS nepoužívají, proto jen 12 čtení)
//==============================================================================================
AF3 Ps2CasScale(AU2 ip, AU4 c0, AU4 c1)
{
    AF2 pp = AF2(ip) * AF2_AU2(c0.xy) + AF2_AU2(c0.zw);
    AF2 fp = floor(pp);
    pp -= fp;
    ASU2 sp = ASU2(fp);

    AF3 b = CasLoad(sp + ASU2( 0,-1));
    AF3 c = CasLoad(sp + ASU2( 1,-1));
    AF3 e = CasLoad(sp + ASU2(-1, 0));
    AF3 f = CasLoad(sp);
    AF3 g = CasLoad(sp + ASU2( 1, 0));
    AF3 h = CasLoad(sp + ASU2( 2, 0));
    AF3 i = CasLoad(sp + ASU2(-1, 1));
    AF3 j = CasLoad(sp + ASU2( 0, 1));
    AF3 k = CasLoad(sp + ASU2( 1, 1));
    AF3 l = CasLoad(sp + ASU2( 2, 1));
    AF3 n = CasLoad(sp + ASU2( 0, 2));
    AF3 o = CasLoad(sp + ASU2( 1, 2));

    // Hard min a max kříže kolem každého středu (f,g,j,k); váhy se počítají jen z kanálu G.
    // Počítá se z gamma hodnot, z rozsahu se bere coring; do lineárního prostoru se pak převádí
    // jen min a max (kvadrát je monotónní).
    AF1 mnfG = AMin3F1(AMin3F1(b.g, e.g, f.g), g.g, j.g);
    AF1 mxfG = AMax3F1(AMax3F1(b.g, e.g, f.g), g.g, j.g);
    AF1 mngG = AMin3F1(AMin3F1(c.g, f.g, g.g), h.g, k.g);
    AF1 mxgG = AMax3F1(AMax3F1(c.g, f.g, g.g), h.g, k.g);
    AF1 mnjG = AMin3F1(AMin3F1(f.g, i.g, j.g), k.g, n.g);
    AF1 mxjG = AMax3F1(AMax3F1(f.g, i.g, j.g), k.g, n.g);
    AF1 mnkG = AMin3F1(AMin3F1(g.g, j.g, k.g), l.g, o.g);
    AF1 mxkG = AMax3F1(AMax3F1(g.g, j.g, k.g), l.g, o.g);

    AF1 coreF = Ps2Core(mxfG - mnfG);
    AF1 coreG = Ps2Core(mxgG - mngG);
    AF1 coreJ = Ps2Core(mxjG - mnjG);
    AF1 coreK = Ps2Core(mxkG - mnkG);

#if PS2_LINEAR_SCALE
    b *= b; c *= c; e *= e; f *= f; g *= g; h *= h;
    i *= i; j *= j; k *= k; l *= l; n *= n; o *= o;
    mnfG *= mnfG; mxfG *= mxfG; mngG *= mngG; mxgG *= mxgG;
    mnjG *= mnjG; mxjG *= mxjG; mnkG *= mnkG; mxkG *= mxkG;
#endif

    AF1 ampfG = APrxLoSqrtF1(ASatF1(min(mnfG, AF1_(1.0) - mxfG) * APrxLoRcpF1(mxfG)));
    AF1 ampgG = APrxLoSqrtF1(ASatF1(min(mngG, AF1_(1.0) - mxgG) * APrxLoRcpF1(mxgG)));
    AF1 ampjG = APrxLoSqrtF1(ASatF1(min(mnjG, AF1_(1.0) - mxjG) * APrxLoRcpF1(mxjG)));
    AF1 ampkG = APrxLoSqrtF1(ASatF1(min(mnkG, AF1_(1.0) - mxkG) * APrxLoRcpF1(mxkG)));

    // Tvar filtru:  0 w 0 / w 1 w / 0 w 0   (w = amp * peak)
    AF1 peak = AF1_AU1(c1.x);
    AF1 wfG = ampfG * peak;
    AF1 wgG = ampgG * peak;
    AF1 wjG = ampjG * peak;
    AF1 wkG = ampkG * peak;

    // Bilineární váhy čtyř výsledků.
    //  s t
    //  u v
    AF1 s = (AF1_(1.0) - pp.x) * (AF1_(1.0) - pp.y);
    AF1 t =              pp.x  * (AF1_(1.0) - pp.y);
    AF1 u = (AF1_(1.0) - pp.x) *              pp.y ;
    AF1 v =              pp.x  *              pp.y ;
    // Ztenčení hran, aby bilineární interpolace nebyla vidět (pomáhá u diagonál).
    AF1 thinB = AF1_(1.0 / 32.0);
    s *= APrxLoRcpF1(thinB + (mxfG - mnfG));
    t *= APrxLoRcpF1(thinB + (mxgG - mngG));
    u *= APrxLoRcpF1(thinB + (mxjG - mnjG));
    v *= APrxLoRcpF1(thinB + (mxkG - mnkG));

    // Finální váhy jednotlivých čtení (stejné jako v ffx_cas.h).
    AF1 qbe = wfG * s;
    AF1 qch = wgG * t;
    AF1 qf  = wgG * t + wjG * u + s;
    AF1 qg  = wfG * s + wkG * v + t;
    AF1 qj  = wfG * s + wkG * v + u;
    AF1 qk  = wgG * t + wjG * u + v;
    AF1 qin = wjG * u;
    AF1 qlo = wkG * v;

    AF1 rcpWG = APrxMedRcpF1(AF1_(2.0) * qbe + AF1_(2.0) * qch + AF1_(2.0) * qin + AF1_(2.0) * qlo + qf + qg + qj + qk);
    AF3 pix = clamp((b * qbe + e * qbe + c * qch + h * qch + i * qin + n * qin + l * qlo + o * qlo + f * qf + g * qg + j * qj + k * qk) * rcpWG, AF1_(0.0), AF1_(1.0));

    // Coring jako "brána": ostřicí jádro CAS má pro 4 středy jednu společnou normalizaci (efektivní
    // váha středu je s*(1+4w)), takže vynulování w jen u některých středů by posunulo interpolaci
    // a změnilo tvar hran. Váhy proto zůstávají původní a coring jen rozhoduje, jestli se použije
    // výsledek filtru, nebo prostá interpolace (tatáž thin-edge váha s,t,u,v, tedy CAS s w=0).
    // Plné ostření zůstane všude, kde je aspoň jeden ze 4 středů nad úrovní šumu.
#if PS2_CORING
    AF1 coreAny = max(max(coreF, coreG), max(coreJ, coreK));
    AF3 plain = (f * s + g * t + j * u + k * v) * (AF1_(1.0) / (s + t + u + v));
    pix = mix(plain, pix, coreAny);
#endif

#if PS2_LINEAR_SCALE
    pix = sqrt(pix);
#endif
    return pix;
}

void Ps2Filter(AU2 gxy)
{
    AF4 c;
    c.a = AF1_(1.0);
    if (sharpenOnly != 0)
        c.rgb = Ps2CasSharpen(gxy, const1);
    else
        c.rgb = Ps2CasScale(gxy, const0, const1);
    imageStore(imgDst, ASU2(gxy), c);
}

layout(local_size_x=64) in;
void main()
{
    // Do remapping of local xy in workgroup for a more PS-like swizzle pattern.
    AU2 gxy = ARmp8x8(gl_LocalInvocationID.x)+AU2(gl_WorkGroupID.x<<4u,gl_WorkGroupID.y<<4u);

    // Každé vlákno zpracuje 4 pixely (čtverce 8x8 v dlaždici 16x16).
    Ps2Filter(gxy);
    gxy.x += 8u;

    Ps2Filter(gxy);
    gxy.y += 8u;

    Ps2Filter(gxy);
    gxy.x -= 8u;

    Ps2Filter(gxy);
}
